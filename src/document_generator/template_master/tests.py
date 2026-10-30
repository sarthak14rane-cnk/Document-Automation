"""template_master test suite — engine unit tests + API tests (plan §4).

Covers:
- engine.computed: golden-format parity (ordinal_date '1st October ,2026',
  financial_year '26-27', indian_format 'Rs. 20,25,000', milestone_amounts
  'Rs.   607500', list_phrase).
- engine.manifest: real config loads; path safety; ConfigError for missing
  keys, AI-block fallbacks and dead library keys.
- engine.schema_builder: 9 groups, toggle items incl. phase_4 'optional',
  3 ai_sections with prompts + requires, identity base fields.
- engine.context_builder: toggle gating, phase_4 optional, gate_by_flag,
  override_input precedence, overrides_from bullets, missing AI content
  with block ids, unknown/required input errors.
- engine.ai_bridge: mocked subprocess.run — plain text, fenced JSON,
  invalid-after-retry -> AIError, timeout -> AIError, model passthrough;
  D1-D3 fixes: binary resolution (PATH .exe preference, npm-shim target
  parse, missing -> AIError, explicit path wins), flags-before-prompt
  argv, <tool_use> debris strip + AI_BRIDGE_DEBRIS_STRIPPED log,
  AI_BRIDGE_MODEL_MISMATCH warning.
- engine.smartart + renderer: real master render; only mapped diagram nodes
  change, all other package entries byte-identical; D4 escaping fidelity
  (& / < > values verbatim in the docxtpl render, SmartArt keeps the raw
  context).
- API: list excludes bogus rows, schema 200/404/409, preview 200 docx
  (opens as zip, contains rendered golden-format strings) / 400
  missing_ai_content, AI view 200 (mocked) / 400 / 502.

The clients app has one pre-existing known test-only failure
(test_create_readonly_fields_ignored) that is intentionally untouched here.
"""

import io
import json
import os
import tempfile
import zipfile
from datetime import date
from pathlib import Path
from unittest import mock, skipUnless

from django.test import TestCase
from loguru import logger
from rest_framework.test import APITestCase

from engine import computed
from engine.ai_bridge import AIError, generate_section, normalize_model, resolve_opencode_bin
from engine.context_builder import InputValidationError, MissingAIContentError, build_context
from engine.errors import ConfigError, RenderError
from engine.manifest import load_config, resolve_under_documents_root
from engine.renderer import render_document
from engine.schema_builder import build_form_schema
from engine.smartart import patch_smartart

from .models import TemplateMaster

CONFIG_PATH = "documents/config_v2.yaml"
TEMPLATE_PATH = "documents/master_dpdpa_ia_v2.docx"

_AI_BLOCK_IDS = ("client_profile", "categories", "processing_bullets")


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def load_v2_config():
    return load_config(CONFIG_PATH)


def full_inputs(**overrides):
    """A small complete input set: every config field satisfied."""
    inputs = {
        "client.name": "Acme Eye Care Foundation",
        "client.short_name": "Acme",
        "client.address_lines": ["12 Vision Street", "Mumbai 400001"],
        "client.contact.salutation": "Mr.",
        "client.contact.name": "R. Mehta",
        "client.website": "https://acme.example",
        "client.entities": ["Acme Trust", "Acme Clinics LLP"],
        "client.profile": "",
        "client.stakeholder_roles": [
            "Medical Director", "Program Lead", "HR Head", "IT Head", "Finance Head",
        ],
        "client.flags": {"processes_children_data": True},
        "reference_number": "CNK/PROP/C/50/26-27",
        "proposal_date": "2026-10-01",
        "validity_days": 15,
        "scope.phases": {},
        "scope.addons": {},
        "scope.bullet_overrides": {},
        "commercials.total_fee": 2025000,
        "commercials.milestones": [
            {"label": "Engagement Initiation", "percent": 30},
            {"label": "Draft Report Presentation", "percent": 40},
            {"label": "Final Report Submission", "percent": 30},
        ],
        "timeline.duration_weeks": "10",
        "timeline.reporting.weekly_day": "Tuesday",
        "timeline.reporting.monthly": "Last working day",
        "retention.working_papers_years": 1,
        "retention.reports_years": 2,
        "ai.industries": ["Eye Care", "Community Outreach"],
        "narrative.outcome_closing": "",
        "narrative.timeline_context": "",
        "narrative.conclusion_context": "",
        "cnk.partner.name": "A. Partner",
        "cnk.partner.designation": "Partner",
        "cnk.partner.email": "partner@cnk.example",
        "cnk.partner.phone": "+91 90000 00000",
        "cnk.joint_partner.enabled": True,
        "cnk.joint_partner.name": "B. Jointer",
        "cnk.joint_partner.short": "BJ",
    }
    inputs.update(overrides)
    return inputs


def sample_ai_content(config=None):
    """Schema-shaped content for every AI block declared in the config."""
    config = config or load_v2_config()
    content = {}
    for section in config["sections"]:
        for block in section["blocks"]:
            if block.get("source") != "ai":
                continue
            schema = block["output_schema"]
            if schema == "text":
                content[block["id"]] = "Generated two-paragraph client profile."
            elif schema == "bullets":
                content[block["id"]] = ["Generated bullet one.", "Generated bullet two."]
            else:  # categories
                content[block["id"]] = [
                    {
                        "id": "contact_data",
                        "title": "Contact Data",
                        "summary": "Identity and contact details of patients and staff.",
                        "bullets": ["Names", "Phone numbers"],
                    },
                    {
                        "id": "children_data",
                        "title": "Children's Data",
                        "summary": "Minor beneficiaries in outreach programmes.",
                        "bullets": ["Age records"],
                        "requires_flag": "processes_children_data",
                    },
                ]
    return content


# ---------------------------------------------------------------------------
# engine.computed
# ---------------------------------------------------------------------------

class ComputedTests(TestCase):
    def test_ordinal_date_golden(self):
        self.assertEqual(computed.ordinal_date("2026-10-01"), "1st October ,2026")
        self.assertEqual(computed.ordinal_date("2026-10-22"), "22nd October ,2026")
        self.assertEqual(computed.ordinal_date("2026-10-11"), "11th October ,2026")

    def test_financial_year_golden(self):
        self.assertEqual(computed.financial_year("2026-10-01"), "26-27")
        self.assertEqual(computed.financial_year("2026-03-31"), "25-26")  # FY ends March
        self.assertEqual(computed.financial_year("2026-04-01"), "26-27")  # FY starts April

    def test_indian_format_golden(self):
        self.assertEqual(computed.indian_format(2025000, prefix="Rs. "), "Rs. 20,25,000")
        self.assertEqual(computed.indian_format(500, prefix="Rs. "), "Rs. 500")
        self.assertEqual(computed.indian_format(100000), "1,00,000")

    def test_milestone_amounts_golden(self):
        rows = computed.milestone_amounts(
            2025000,
            [
                {"label": "Engagement Initiation", "percent": 30},
                {"label": "Draft Report Presentation", "percent": 40},
            ],
        )
        # Verbatim golden table-cell format: 'Rs.' + 3 spaces + ungrouped digits.
        self.assertEqual(rows[0]["amount_indian"], "Rs.   607500")
        self.assertEqual(rows[1]["amount_indian"], "Rs.   810000")
        self.assertEqual(rows[0]["label"], "Engagement Initiation")
        self.assertEqual(rows[0]["percent"], 30)

    def test_list_phrase(self):
        self.assertEqual(computed.list_phrase(["Eye Care", "Community Outreach"]), "Eye Care and Community Outreach")
        self.assertEqual(computed.list_phrase(["A", "B", "C"]), "A, B and C")
        self.assertEqual(computed.list_phrase([], fallback="the organisation"), "the organisation")


# ---------------------------------------------------------------------------
# engine.manifest
# ---------------------------------------------------------------------------

class ManifestTests(TestCase):
    def test_real_config_loads(self):
        config = load_v2_config()
        self.assertEqual(config["service"], "DPDPA_IA")
        self.assertTrue(config["sections"])
        self.assertIn("total_fee_indian", config["computed"])

    def test_path_safety(self):
        # Relative path inside the documents root resolves under DOCUMENTS_ROOT.
        resolved = resolve_under_documents_root(CONFIG_PATH)
        self.assertTrue(str(resolved).endswith("config_v2.yaml"))
        # Absolute paths and '..' escapes are rejected.
        with self.assertRaises(ConfigError):
            resolve_under_documents_root("C:/Windows/system32/config.yaml")
        with self.assertRaises(ConfigError):
            resolve_under_documents_root("../../etc/passwd")
        with self.assertRaises(ConfigError):
            resolve_under_documents_root("documents/../../secrets.yaml")

    def test_load_missing_file_raises(self):
        with self.assertRaises(ConfigError):
            load_config("documents/__definitely_missing__.yaml")

    def test_missing_top_key(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "x.yaml").write_text("version: 1\n", encoding="utf-8")
            with self.assertRaises(ConfigError) as ctx:
                load_config("x.yaml", documents_root=tmp)
        self.assertIn("inputs", str(ctx.exception))

    def test_ai_block_with_fallback_rejected(self):
        block = {
            "id": "b1", "source": "ai", "type": "text",
            "prompt": "Generate", "output_schema": "text", "fallback": "library.something",
        }
        errors = []
        from engine.manifest import _validate_block
        _validate_block("test", block, errors)
        self.assertTrue(any("fallback" in e for e in errors))

    def test_dead_library_key_rejected(self):
        config = {
            "version": 1,
            "inputs": [{"group": "g", "title": "G", "fields": [{"key": "a", "type": "text"}]}],
            "computed": {},
            "sections": [
                {
                    "id": "s1", "group": "g",
                    "blocks": [{"id": "b1", "source": "config_ref", "type": "text", "path": "library.used.intro"}],
                }
            ],
            "library": {"used": {"intro": "x"}, "dead_key": {"y": 1}},
        }
        from engine.manifest import _validate_library_references
        errors = []
        _validate_library_references(config, errors)
        self.assertTrue(any("dead_key" in e for e in errors))

    def test_unknown_computed_function_rejected(self):
        from engine.manifest import _validate_computed
        errors = []
        _validate_computed({"computed": {"x": {"fn": "no_such_fn", "args": {}}}}, errors)
        self.assertTrue(any("no_such_fn" in e for e in errors))


# ---------------------------------------------------------------------------
# engine.schema_builder
# ---------------------------------------------------------------------------

class SchemaBuilderTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.config = load_v2_config()
        cls.schema = build_form_schema(cls.config)

    def test_nine_groups_present(self):
        group_keys = [g["group"] for g in self.schema["groups"]]
        self.assertEqual(
            group_keys,
            [
                "client", "reference", "scope", "commercials", "timeline",
                "retention", "ai_context", "narrative", "cnk",
            ],
        )

    def test_toggle_items_include_optional_phase_4(self):
        scope_group = next(g for g in self.schema["groups"] if g["group"] == "scope")
        phases_field = next(f for f in scope_group["fields"] if f["key"] == "scope.phases")
        items = {item["key"]: item["default"] for item in phases_field["items"]}
        self.assertEqual(items["phase_4"], "optional")
        self.assertTrue(items["phase_1"])

    def test_three_ai_sections_with_prompts_and_requires(self):
        ai = {s["block_id"]: s for s in self.schema["ai_sections"]}
        self.assertEqual(
            set(ai), {"client_profile", "categories", "processing_bullets"}
        )
        profile = ai["client_profile"]
        self.assertEqual(profile["output_schema"], "text")
        self.assertIn("{{ client.name }}", profile["prompt"])
        for required in ("client.name", "computed.entities_phrase", "ai.industries_phrase"):
            self.assertIn(required, profile["requires"])
        categories = ai["categories"]
        self.assertEqual(categories["output_schema"], "categories")
        self.assertEqual(categories["grounding"], True)

    def test_identity_base_fields(self):
        keys = [f["key"] for f in self.schema["base_fields"]]
        self.assertEqual(keys, ["service", "version", "client_id", "created_by"])
        service = self.schema["base_fields"][0]
        self.assertEqual(service["value"], "DPDPA_IA")
        self.assertTrue(service["fixed"])


# ---------------------------------------------------------------------------
# engine.context_builder
# ---------------------------------------------------------------------------

class ContextBuilderTests(TestCase):
    def build(self, **overrides):
        config = load_v2_config()
        inputs = full_inputs(**overrides)
        return build_context(config, inputs, sample_ai_content(config))

    def test_computed_merges_and_golden_values(self):
        context = self.build()
        self.assertEqual(context["total_fee_indian"], "Rs. 20,25,000")
        self.assertEqual(context["proposal_date_ordinal"], "1st October ,2026")
        self.assertEqual(context["financial_year"], "26-27")
        self.assertEqual(context["computed"]["financial_year"], "26-27")
        self.assertEqual(context["milestones"][0]["amount_indian"], "Rs.   607500")

    def test_ai_industries_phrase_alias(self):
        context = self.build()
        self.assertEqual(context["ai"]["industries_phrase"], "Eye Care and Community Outreach")

    def test_uniform_block_payload_keys(self):
        context = self.build()
        for section in context["sections"].values():
            for payload in section["blocks"]:
                for key in ("text", "paragraphs", "bullets", "entries", "categories"):
                    self.assertIn(key, payload)

    def test_section_payloads_populated(self):
        context = self.build()
        self.assertEqual(
            context["sections"]["entity_coverage"]["by_id"]["entity_list"]["entries"],
            ["Acme Trust", "Acme Clinics LLP"],
        )
        self.assertEqual(
            context["sections"]["expected_outcome"]["by_id"]["items"]["entries"][0]["title"],
            "DPDP Compliance Readiness",
        )
        self.assertEqual(
            context["sections"]["standard_terms"]["by_id"]["clauses"]["entries"][0]["title"],
            "Confidentiality",
        )
        self.assertTrue(
            context["sections"]["annexure_definitions"]["by_id"]["definitions"]["paragraphs"]
        )
        self.assertEqual(
            context["sections"]["remuneration"]["by_id"]["milestones_table"]["columns"][0]["header"],
            "Details",
        )

    def test_ai_content_bound(self):
        context = self.build()
        self.assertEqual(
            context["sections"]["entity_coverage"]["by_id"]["client_profile"]["text"],
            "Generated two-paragraph client profile.",
        )
        cats = context["sections"]["data_categories"]["by_id"]["categories"]["categories"]
        self.assertEqual(cats[0]["title"], "Contact Data")

    def test_gate_by_flag_keeps_children_data_when_flag_true(self):
        context = self.build()
        cats = context["sections"]["data_categories"]["by_id"]["categories"]["categories"]
        self.assertIn("children_data", [c["id"] for c in cats])

    def test_gate_by_flag_drops_children_data_when_flag_false(self):
        context = self.build(**{"client.flags": {"processes_children_data": False}})
        cats = context["sections"]["data_categories"]["by_id"]["categories"]["categories"]
        self.assertNotIn("children_data", [c["id"] for c in cats])

    def test_disabled_phase_is_blanked(self):
        context = self.build(**{"scope.phases": {"phase_2a": False}})
        self.assertEqual(context["phases"]["phase_2a"]["title"], "")
        self.assertEqual(context["sections"]["phase_2a"]["blocks"], [])
        self.assertEqual(context["sections"]["phase_2a"]["heading"], "")
        # Enabled phases still carry content.
        self.assertTrue(context["phases"]["phase_1"]["title"])
        self.assertTrue(context["phases"]["phase_1"]["bullets"])

    def test_phase_4_optional_renders_enabled(self):
        context = self.build()  # phase_4 default is 'optional'
        self.assertTrue(context["phases"]["phase_4"]["title"])
        self.assertTrue(context["phases"]["phase_4"]["disclaimer"])

    def test_phase_4_off_is_blanked(self):
        context = self.build(**{"scope.phases": {"phase_4": False}})
        self.assertEqual(context["phases"]["phase_4"]["title"], "")

    def test_override_input_user_value_wins(self):
        context = self.build(**{"narrative.timeline_context": "Custom timeline note."})
        self.assertEqual(
            context["sections"]["timelines"]["by_id"]["timeline_context"]["text"],
            "Custom timeline note.",
        )

    def test_override_input_falls_back_to_default(self):
        context = self.build()
        self.assertIn("obligations apply", context["sections"]["timelines"]["by_id"]["timeline_context"]["text"])

    def test_overrides_from_add_remove_bullets(self):
        first = self.build()
        removed_bullet = first["phases"]["phase_1"]["bullets"][0]
        context = self.build(**{
            "scope.bullet_overrides": {
                "phase_1": {"remove": [removed_bullet], "add": ["Custom extra bullet."]},
            }
        })
        self.assertNotIn(removed_bullet, context["phases"]["phase_1"]["bullets"])
        self.assertIn("Custom extra bullet.", context["phases"]["phase_1"]["bullets"])

    def test_addon_toggle_filters_boxes(self):
        context = self.build(**{"scope.addons": {"dpo_service": False}})
        titles = [e["title"] for e in context["sections"]["addons"]["by_id"]["boxes"]["entries"]]
        self.assertNotIn("Data Protection Officer as a Service", titles)
        self.assertIn("Lightweight RoPA Implementation", titles)

    def test_addon_paragraphs_rendered(self):
        context = self.build()
        ropa = next(
            e for e in context["sections"]["addons"]["by_id"]["boxes"]["entries"]
            if e["title"] == "Lightweight RoPA Implementation"
        )
        self.assertIn("practical and maintainable register", ropa["paragraphs"][0])

    def test_missing_ai_content_lists_all_block_ids(self):
        config = load_v2_config()
        with self.assertRaises(MissingAIContentError) as ctx:
            build_context(config, full_inputs(), {})
        self.assertEqual(sorted(ctx.exception.block_ids), sorted(_AI_BLOCK_IDS))

    def test_ai_block_validates_schema(self):
        config = load_v2_config()
        content = sample_ai_content(config)
        content["processing_bullets"] = "not a list"
        with self.assertRaises(InputValidationError) as ctx:
            build_context(config, full_inputs(), content)
        self.assertIn("ai_content.processing_bullets", ctx.exception.messages)

    def test_unknown_input_key_rejected(self):
        config = load_v2_config()
        with self.assertRaises(InputValidationError) as ctx:
            build_context(config, full_inputs(**{"bogus.key": "x"}), sample_ai_content(config))
        self.assertIn("bogus.key", ctx.exception.messages)

    def test_required_inputs_enforced(self):
        config = load_v2_config()
        with self.assertRaises(InputValidationError) as ctx:
            build_context(config, full_inputs(**{"client.name": "", "commercials.total_fee": None}),
                          sample_ai_content(config))
        messages = ctx.exception.messages
        self.assertIn("client.name", messages)
        self.assertIn("commercials.total_fee", messages)

    def test_milestone_input_coercion(self):
        context = self.build()
        self.assertEqual(len(context["commercials"]["milestones"]), 3)
        self.assertEqual(context["milestones"][1]["percent"], 40)


# ---------------------------------------------------------------------------
# engine.ai_bridge (mocked subprocess)
# ---------------------------------------------------------------------------

def _ndjson(*events):
    return "\n".join(json.dumps(event) for event in events) + "\n"


def _text_event(text):
    return {"type": "text", "part": {"type": "text", "text": text}}


class AIBridgeTests(TestCase):
    def setUp(self):
        super().setUp()
        # D1: keep generate_section independent of this machine's PATH; the
        # dedicated test_resolve_bin_* tests below call the REAL resolver.
        patcher = mock.patch(
            "engine.ai_bridge.resolve_opencode_bin", return_value="opencode"
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def _run_mock(self, stdout="", returncode=0, side_effect=None):
        proc = mock.Mock(returncode=returncode, stdout=stdout, stderr="")
        patcher = mock.patch("engine.ai_bridge.subprocess.run", return_value=proc, side_effect=side_effect)
        return patcher

    def test_normalize_model(self):
        self.assertEqual(normalize_model("fast-model"), "opencode/fast-model")
        self.assertEqual(normalize_model("go/fast-model"), "go/fast-model")
        self.assertIsNone(normalize_model(""))
        self.assertIsNone(normalize_model(None))

    def test_text_output(self):
        stdout = _ndjson(
            {"type": "step_start", "part": {"type": "step-start"}},
            _text_event("Plain summary."),
        )
        with self._run_mock(stdout=stdout):
            self.assertEqual(generate_section("p", "text"), "Plain summary.")

    def test_fenced_json_bullets(self):
        payload = json.dumps(["Bullet A", "Bullet B"])
        stdout = _ndjson(_text_event(f"```json\n{payload}\n```"))
        with self._run_mock(stdout=stdout):
            self.assertEqual(generate_section("p", "bullets"), ["Bullet A", "Bullet B"])

    def test_categories_output(self):
        payload = json.dumps([
            {"id": "c1", "title": "Cat", "summary": "S.", "bullets": ["b1"]},
        ])
        stdout = _ndjson(_text_event(payload))
        with self._run_mock(stdout=stdout):
            content = generate_section("p", "categories")
        self.assertEqual(content[0]["title"], "Cat")

    def test_invalid_output_retries_then_raises(self):
        stdout = _ndjson(_text_event("```json\n{not json}\n```"))
        with self._run_mock(stdout=stdout) as run_mock:
            with self.assertRaises(AIError):
                generate_section("p", "bullets")
        self.assertEqual(run_mock.call_count, 2)  # one full retry

    def test_empty_output_after_retry_raises(self):
        stdout = _ndjson(_text_event("  "))
        with self._run_mock(stdout=stdout):
            with self.assertRaises(AIError):
                generate_section("p", "text")

    def test_timeout_raises_immediately(self):
        import subprocess as subprocess_module

        with self._run_mock(side_effect=subprocess_module.TimeoutExpired(cmd="opencode", timeout=1)):
            with self.assertRaises(AIError):
                generate_section("p", "text")

    def test_model_and_format_json_argv(self):
        stdout = _ndjson(_text_event("ok"))
        with self._run_mock(stdout=stdout) as run_mock:
            generate_section("p", "text", model="fast-model")
        argv = run_mock.call_args.args[0]
        self.assertIn("--format", argv)
        self.assertIn("json", argv)
        self.assertIn("--model", argv)
        self.assertEqual(argv[argv.index("--model") + 1], "opencode/fast-model")

    def test_nonzero_exit_retries_then_raises(self):
        with self._run_mock(stdout="", returncode=1) as run_mock:
            with self.assertRaises(AIError):
                generate_section("p", "text")
        self.assertEqual(run_mock.call_count, 2)

    # -- D1/D3: binary resolution + argv order ------------------------------

    def test_resolve_bin_prefers_exe_on_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe = Path(tmp) / "fakeopencode.exe"
            shim = Path(tmp) / "fakeopencode.cmd"
            exe.write_text("")
            shim.write_text(r'"%dp0%\node_modules\cli\fakeopencode.exe" %*')
            with mock.patch.dict(os.environ, {"PATH": tmp}):
                resolved = resolve_opencode_bin("fakeopencode")
            self.assertEqual(
                os.path.normcase(resolved), os.path.normcase(str(exe))
            )

    @skipUnless(os.name == "nt", "npm .cmd shims are a Windows concept")
    def test_resolve_bin_parses_npm_shim(self):
        with tempfile.TemporaryDirectory() as tmp:
            shim = Path(tmp) / "opencode.cmd"
            target = Path(tmp) / "node_modules" / "cli" / "opencode.exe"
            target.parent.mkdir(parents=True)
            target.write_text("")
            shim.write_text(
                "@ECHO off\n" + r'"%dp0%\node_modules\cli\opencode.exe"   %*'
            )
            with mock.patch.dict(os.environ, {"PATH": tmp}):
                resolved = resolve_opencode_bin("opencode")
            self.assertEqual(
                os.path.normcase(resolved), os.path.normcase(str(target))
            )

    def test_resolve_bin_missing_raises_aierror(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"PATH": tmp}):
                with self.assertRaises(AIError) as ctx:
                    resolve_opencode_bin("no-such-opencode-xyz")
        self.assertIn("OPENCODE_BIN", str(ctx.exception))

    def test_resolve_bin_explicit_path_wins(self):
        here = os.path.abspath(__file__)
        self.assertEqual(resolve_opencode_bin(here), here)  # existing file
        missing = os.path.join("does-not-exist", "opencode")
        self.assertEqual(resolve_opencode_bin(missing), missing)  # path separator

    def test_argv_puts_flags_before_prompt(self):
        stdout = _ndjson(_text_event("ok"))
        with self._run_mock(stdout=stdout) as run_mock:
            generate_section("line one\nline two", "text", model="fast-model")
        argv = run_mock.call_args.args[0]
        self.assertEqual(argv[0], "opencode")  # setUp-patched resolution
        self.assertEqual(
            argv[1:6],
            ["run", "--format", "json", "--model", "opencode/fast-model"],
        )
        self.assertEqual(argv[6], "line one\nline two")  # prompt LAST
        self.assertEqual(len(argv), 7)

    # -- D2: tool-debris stripping + D3: mismatch warning -------------------

    def test_text_debris_stripped_and_logged(self):
        debris = (
            "<tool_use><tool_name>read</tool_name>"
            "<tool_input>{}</tool_input></tool_use>"
        )
        stdout = _ndjson(_text_event(f"PONG\n\n{debris}"))
        records = []
        sink = logger.add(records.append, level="WARNING")
        try:
            with self._run_mock(stdout=stdout):
                result = generate_section("p", "text")
        finally:
            logger.remove(sink)
        self.assertEqual(result, "PONG")
        self.assertTrue(
            any("AI_BRIDGE_DEBRIS_STRIPPED" in str(record) for record in records)
        )

    def test_debris_around_json_still_parses(self):
        payload = json.dumps(["Bullet A", "Bullet B"])
        stdout = _ndjson(
            _text_event(f"<tool_use>noise</tool_use>\n```json\n{payload}\n```")
        )
        with self._run_mock(stdout=stdout):
            self.assertEqual(
                generate_section("p", "bullets"), ["Bullet A", "Bullet B"]
            )

    def test_model_mismatch_warns(self):
        stdout = _ndjson(
            {
                "type": "text",
                "part": {"type": "text", "text": "ok", "modelID": "other/model"},
            }
        )
        records = []
        sink = logger.add(records.append, level="WARNING")
        try:
            with self._run_mock(stdout=stdout):
                result = generate_section("p", "text", model="fast-model")
        finally:
            logger.remove(sink)
        self.assertEqual(result, "ok")
        self.assertTrue(
            any(
                "AI_BRIDGE_MODEL_MISMATCH" in str(record)
                and "other/model" in str(record)
                for record in records
            )
        )


# ---------------------------------------------------------------------------
# engine.smartart + engine.renderer (real master render)
# ---------------------------------------------------------------------------

_DGM = "http://schemas.openxmlformats.org/drawingml/2006/diagram"
_A = "http://schemas.openxmlformats.org/drawingml/2006/main"


def _fake_diagram():
    """4 data paragraphs: ROLE0..ROLE3."""
    paragraphs = "".join(
        f'<a:p xmlns:a="{_A}"><a:r><a:t>ROLE{i}</a:t></a:r></a:p>' for i in range(4)
    )
    node = (
        f'<dgm:dataModel xmlns:dgm="{_DGM}">'
        f'<dgm:pt modelId="d1" type="doc"/>'
        f'<dgm:pt modelId="d2"><dgm:t>{paragraphs}</dgm:t></dgm:pt>'
        f'</dgm:dataModel>'
    )
    return node.encode("utf-8")


class SmartArtTests(TestCase):
    def _package(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("word/document.xml", "<doc/>")
            archive.writestr("word/diagrams/data2.xml", _fake_diagram())
            archive.writestr("word/media/image1.png", b"\x89PNG-fake-bytes")
        return buffer.getvalue()

    def test_only_mapped_nodes_and_parts_change(self):
        original = self._package()
        config = {
            "smartart": {
                "word/diagrams/data2.xml": [
                    {"nodes": [0], "source": {"input": "client.name"}},
                    {"nodes": [1], "source": {"input": "timeline.reporting.weekly_day",
                                              "format": "Weekly {value_upper} "}},
                    {"nodes": [2], "source": {"input": "timeline.reporting.monthly"},
                     "skip_if_empty": True},
                    {"nodes": [9], "source": {"input": "client.name"}},  # out of range
                ]
            }
        }
        context = {
            "client": {"name": "Acme"},
            "timeline": {"reporting": {"weekly_day": "Tuesday", "monthly": ""}},
        }
        patched = patch_smartart(original, config, context)

        with zipfile.ZipFile(io.BytesIO(original)) as before, zipfile.ZipFile(
            io.BytesIO(patched)
        ) as after:
            self.assertEqual(before.namelist(), after.namelist())
            # Non-diagram entries are byte-identical.
            self.assertEqual(before.read("word/document.xml"), after.read("word/document.xml"))
            self.assertEqual(before.read("word/media/image1.png"), after.read("word/media/image1.png"))
            diagram = after.read("word/diagrams/data2.xml").decode("utf-8")
        # Mapped nodes changed.
        self.assertIn(">Acme<", diagram)
        self.assertIn("Weekly TUESDAY ", diagram)
        # skip_if_empty left the node untouched; out-of-range skipped.
        self.assertIn("ROLE2", diagram)
        self.assertIn("ROLE3", diagram)

    def test_missing_part_raises(self):
        with self.assertRaises(RenderError):
            patch_smartart(self._package(), {"smartart": {"word/diagrams/nope.xml": []}}, {})


class RendererTests(TestCase):
    """E2E engine render against the real master + config (golden parity)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.config = load_v2_config()
        cls.template_path = resolve_under_documents_root(TEMPLATE_PATH)

    def test_render_produces_docx_with_golden_strings(self):
        context = build_context(self.config, full_inputs(), sample_ai_content(self.config))
        docx_bytes = render_document(self.config, self.template_path, context)
        self.assertTrue(docx_bytes.startswith(b"PK"))  # zip magic
        with zipfile.ZipFile(io.BytesIO(docx_bytes)) as archive:
            document = archive.read("word/document.xml").decode("utf-8")
            data2 = archive.read("word/diagrams/data2.xml").decode("utf-8")
            data3 = archive.read("word/diagrams/data3.xml").decode("utf-8")
        # Golden-format parity strings (A4) + core bindings.
        self.assertIn("1st October ,2026", document)
        self.assertIn("CNK/PROP/C/50/26-27", document)
        self.assertIn("Rs. 20,25,000", document)
        self.assertIn("Acme Eye Care Foundation", document)
        self.assertIn("Rs.   607500", document)
        # SmartArt patches (org chart + reporting cadence + joint partner).
        self.assertIn("Medical Director", data2)
        self.assertIn("BJ PARTNER", data2)
        self.assertIn("Weekly TUESDAY ", data3)
        # Disabled-phase blanking is absent here (all enabled) but the
        # phase bridge bindings must carry real content:
        self.assertIn("Phase 1 DPDP Impact Assessment (Current State Review)", document)

    # -- D4: & / < > fidelity (docxtpl recover-parser protection) ------------

    def _render(self, inputs=None, ai_content=None):
        context = build_context(
            self.config,
            inputs if inputs is not None else full_inputs(),
            ai_content if ai_content is not None else sample_ai_content(self.config),
        )
        return render_document(self.config, self.template_path, context)

    @staticmethod
    def _document_xml(docx_bytes):
        with zipfile.ZipFile(io.BytesIO(docx_bytes)) as archive:
            return archive.read("word/document.xml").decode("utf-8")

    def test_ampersand_value_survives_render(self):
        ai = sample_ai_content(self.config)
        ai["categories"][0]["title"] = "Employee & Workforce Data"
        document = self._document_xml(self._render(ai_content=ai))
        self.assertIn("Employee &amp; Workforce Data", document)
        self.assertNotIn("Employee  Workforce Data", document)  # D4 signature

    def test_angle_bracket_value_renders_literally(self):
        inputs = full_inputs(
            **{
                "client.address_lines": [
                    "12 Vision Street, Tower < 500 records>",
                    "Mumbai 400001",
                ]
            }
        )
        document = self._document_xml(self._render(inputs=inputs))
        self.assertIn("&lt; 500 records", document)

    def test_config_ampersand_phase_titles_survive(self):
        document = self._document_xml(self._render())
        self.assertIn(
            "Governance, Policy &amp; Compliance Framework Design", document
        )
        self.assertIn(
            "Privacy Controls, Technology &amp; Operational Design", document
        )

    def test_smartart_receives_raw_context(self):
        inputs = full_inputs(
            **{"client.stakeholder_roles": ["R&D Head", "Program Lead"]}
        )
        docx_bytes = self._render(inputs=inputs)
        with zipfile.ZipFile(io.BytesIO(docx_bytes)) as archive:
            data2 = archive.read("word/diagrams/data2.xml").decode("utf-8")
        self.assertIn("R&amp;D Head", data2)  # lxml escaped the RAW value
        self.assertNotIn(
            "R&amp;amp;D Head", data2
        )  # would mean the escaped copy leaked into SmartArt


# ---------------------------------------------------------------------------
# API tests
# ---------------------------------------------------------------------------

class TemplateAPITests(APITestCase):
    def setUp(self):
        self.valid_row = TemplateMaster.objects.create(
            template_name="DPDPA Impact Assessment",
            config_path=CONFIG_PATH,
            template_path=TEMPLATE_PATH,
        )
        self.bogus_row = TemplateMaster.objects.create(
            template_name="Broken Template",
            config_path="documents/__missing__.yaml",
            template_path=TEMPLATE_PATH,
        )

    # -- GET /templates/ ----------------------------------------------------

    def test_list_excludes_rows_with_missing_files(self):
        response = self.client.get("/templates/")
        self.assertEqual(response.status_code, 200)
        ids = [row["template_id"] for row in response.data]
        self.assertIn(self.valid_row.template_id, ids)
        self.assertNotIn(self.bogus_row.template_id, ids)

    # -- GET schema ----------------------------------------------------------

    def test_schema_404_unknown(self):
        response = self.client.get("/templates/999999/schema/")
        self.assertEqual(response.status_code, 404)

    def test_schema_404_inactive(self):
        self.valid_row.is_active = False
        self.valid_row.save()
        response = self.client.get(f"/templates/{self.valid_row.template_id}/schema/")
        self.assertEqual(response.status_code, 404)

    def test_schema_409_missing_config_file(self):
        response = self.client.get(f"/templates/{self.bogus_row.template_id}/schema/")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "config_file_missing")

    def test_schema_200_payload(self):
        response = self.client.get(f"/templates/{self.valid_row.template_id}/schema/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["template"]["template_name"], "DPDPA Impact Assessment")
        self.assertEqual(response.data["template"]["service"], "DPDPA_IA")
        self.assertEqual(len(response.data["groups"]), 9)
        self.assertEqual(
            {s["block_id"] for s in response.data["ai_sections"]}, set(_AI_BLOCK_IDS)
        )
        self.assertTrue(all(s["prompt"] for s in response.data["ai_sections"]))

    # -- POST preview ----------------------------------------------------------

    def test_preview_404_unknown(self):
        response = self.client.post("/templates/999999/preview/", {"inputs": {}}, format="json")
        self.assertEqual(response.status_code, 404)

    def test_preview_409_missing_files(self):
        response = self.client.post(
            f"/templates/{self.bogus_row.template_id}/preview/", {"inputs": {}}, format="json"
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "config_file_missing")

    def test_preview_400_unknown_input_key(self):
        response = self.client.post(
            f"/templates/{self.valid_row.template_id}/preview/",
            {"inputs": {"no_such_key": "x"}, "ai_content": sample_ai_content()},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("no_such_key", response.data)

    def test_preview_400_missing_ai_content(self):
        response = self.client.post(
            f"/templates/{self.valid_row.template_id}/preview/",
            {"inputs": full_inputs()},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "missing_ai_content")
        self.assertEqual(sorted(response.data["blocks"]), sorted(_AI_BLOCK_IDS))

    def test_preview_200_rendered_docx(self):
        response = self.client.post(
            f"/templates/{self.valid_row.template_id}/preview/",
            {"inputs": full_inputs(), "ai_content": sample_ai_content()},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Type"],
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        self.assertIn(".docx", response["Content-Disposition"])
        payload = b"".join(response.streaming_content)
        self.assertTrue(payload.startswith(b"PK"))
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            self.assertIn("word/document.xml", archive.namelist())

    def test_preview_400_field_errors_shape(self):
        response = self.client.post(
            f"/templates/{self.valid_row.template_id}/preview/",
            {"inputs": full_inputs(**{"client.name": ""}), "ai_content": sample_ai_content()},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("client.name", response.data)

    # -- POST /ai/generate-section/ --------------------------------------------

    def test_ai_view_malformed_request_400(self):
        response = self.client.post("/ai/generate-section/", {}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_ai_view_unresolved_prompt_vars_400(self):
        response = self.client.post(
            "/ai/generate-section/",
            {
                "prompt": "Summarise {{ proposal_date }} for {{ client.name }}.",
                "output_schema": "text",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "unresolved_prompt_vars")
        self.assertIn("proposal_date", response.data["variables"])

    def test_ai_view_200_with_mocked_bridge(self):
        with mock.patch(
            "template_master.views.generate_section",
            return_value=["Generated bullet one."],
        ) as bridge_mock:
            response = self.client.post(
                "/ai/generate-section/",
                {
                    "prompt": "List processing characteristics for {{ client.name }}.",
                    "output_schema": "bullets",
                    "industries": ["Eye Care"],
                    "client_context": {"name": "Acme Eye Care Foundation"},
                    "model_id": "fast-model",
                },
                format="json",
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["output_schema"], "bullets")
        self.assertEqual(response.data["content"], ["Generated bullet one."])
        bridge_mock.assert_called_once()
        self.assertEqual(bridge_mock.call_args.kwargs.get("model"), "fast-model")

    def test_ai_view_bridge_failure_502(self):
        with mock.patch(
            "template_master.views.generate_section",
            side_effect=AIError("AI generation failed: bad output"),
        ):
            response = self.client.post(
                "/ai/generate-section/",
                {
                    "prompt": "Generate for {{ client.name }}.",
                    "output_schema": "text",
                    "client_context": {"name": "Acme Eye Care Foundation"},
                },
                format="json",
            )
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.data["code"], "ai_generation_failed")
