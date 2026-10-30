"""E2E test: all 4 template_master endpoints with REAL opencode AI generation,
3 industry clients. Rolls back all DB writes. Artifacts -> session dir."""
import io
import json
import os
import sys
import time
import zipfile
from pathlib import Path
from unittest import mock

SESSION = Path(__file__).resolve().parent
REPO = SESSION.parent.parent
sys.path.insert(0, str(REPO / "src" / "document_generator"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")

import django

django.setup()

from django.conf import settings
from django.db import transaction
from django.test import Client
from django.test.utils import setup_test_environment

setup_test_environment()
settings.ALLOWED_HOSTS = list(settings.ALLOWED_HOSTS) + ["testserver"]

from engine.errors import AIError
from template_master.models import TemplateMaster
from template_master.tests import full_inputs

RESULTS = []
AI_SLEEP = 2.0  # be gentle between real model calls


def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    RESULTS.append((name, status, detail))
    suffix = f"  -- {detail}" if (detail and status == "FAIL") else ""
    print(f"  [{status}] {name}{suffix}", flush=True)


def text_of(xml_bytes):
    """Rough visible-text extraction from a wordprocessingml part."""
    import re

    text = xml_bytes.decode("utf-8", "replace")
    text = re.sub(r"<w:p[ >]", "\n<w:p ", text)
    text = re.sub(r"<[^>]+>", "", text)
    return text


# ---------------------------------------------------------------------------
# Client fixtures (3 industries)
# ---------------------------------------------------------------------------
COMMON = dict(
    **{
        "client.short_name": "Acme",
        "client.address_lines": ["12 Vision Street", "Mumbai 400001"],
        "client.contact.salutation": "Mr.",
        "client.contact.name": "R. Mehta",
        "client.website": "https://acme.example",
        "client.profile": "",
        "reference_number": "CNK/PROP/C/50/26-27",
        "proposal_date": "2026-10-01",
        "validity_days": 15,
        "scope.phases": {},
        "scope.addons": {},
        "scope.bullet_overrides": {},
        "commercials.milestones": [
            {"label": "Engagement Initiation", "percent": 30},
            {"label": "Draft Report Presentation", "percent": 40},
            {"label": "Final Report Submission", "percent": 30},
        ],
        "timeline.duration_weeks": "10",
        "retention.working_papers_years": 1,
        "retention.reports_years": 2,
        "narrative.outcome_closing": "",
        "narrative.timeline_context": "",
        "narrative.conclusion_context": "",
        "cnk.partner.name": "A. Partner",
        "cnk.partner.designation": "Partner",
        "cnk.partner.email": "partner@cnk.example",
        "cnk.partner.phone": "+91 90000 00000",
    }
)

CLIENTS = [
    {
        "key": "acme_ngo",
        "overrides": {
            **COMMON,
            "client.name": "Acme Eye Care Foundation",
            "client.short_name": "Acme",
            "client.website": "https://acme.example",
            "client.entities": ["Acme Trust", "Acme Clinics LLP"],
            "client.stakeholder_roles": [
                "Medical Director", "Program Lead", "HR Head", "IT Head", "Finance Head",
            ],
            "client.flags": {"processes_children_data": True},
            "commercials.total_fee": 2025000,
            "timeline.reporting.weekly_day": "Tuesday",
            "timeline.reporting.monthly": "Last working day",
            "ai.industries": ["Eye Care", "Community Outreach"],
            "cnk.joint_partner.enabled": True,
            "cnk.joint_partner.name": "B. Jointer",
            "cnk.joint_partner.short": "BJ",
        },
        "industries": ["Eye Care", "Community Outreach"],
        "expect_fee": "Rs. 20,25,000",
        "expect_milestones": ["Rs.   607500", "Rs.   810000"],
        "weekly": "Weekly TUESDAY",
        "phase4": True,
        "partner_short": "BJ",
        "keep_partner_text": None,
        "industry_keywords": ["eye", "vision", "health", "patient", "clinic"],
    },
    {
        "key": "bharat_manufacturing",
        "overrides": {
            **COMMON,
            "client.name": "Bharat Manufacturing Industries Limited",
            "client.short_name": "Bharat",
            "client.address_lines": ["Plot 17, MIDC Chakan", "Pune 410501"],
            "client.website": "https://bharatmfg.example",
            "client.entities": ["Bharat Steel Limited", "Bharat Logistics LLP"],
            "client.stakeholder_roles": ["Plant Head", "Quality Head", "Legal Head"],
            "client.flags": {"processes_children_data": False},
            "commercials.total_fee": 1500000,
            "timeline.reporting.weekly_day": "Friday",
            "timeline.reporting.monthly": "5th of every month",
            "ai.industries": ["Steel Manufacturing", "Industrial Equipment"],
            "scope.phases": {"phase_4": False},
            "reference_number": "CNK/PROP/B/51/26-27",
            "cnk.joint_partner.enabled": False,
            "cnk.joint_partner.name": "",
            "cnk.joint_partner.short": "",
        },
        "industries": ["Steel Manufacturing", "Industrial Equipment"],
        "expect_fee": "Rs. 15,00,000",
        "expect_milestones": ["Rs.   450000", "Rs.   600000"],
        "weekly": "Weekly FRIDAY",
        "phase4": False,
        "partner_short": None,
        "keep_partner_text": "KLA PARTNER",
        "industry_keywords": ["manufactur", "steel", "industrial", "plant", "vendor"],
    },
    {
        "key": "technova_fintech",
        "overrides": {
            **COMMON,
            "client.name": "TechNova Fintech Private Limited",
            "client.short_name": "TechNova",
            "client.address_lines": ["Tower B, Cyber City", "Gurugram 122002"],
            "client.website": "https://technova.example",
            "client.entities": ["TechNova Payments", "TechNova Credit"],
            "client.stakeholder_roles": [
                "Compliance Officer", "Data Protection Officer", "CTO", "CEO",
            ],
            "client.flags": {"processes_children_data": True},
            "commercials.total_fee": 4800000,
            "timeline.reporting.weekly_day": "Monday",
            "timeline.reporting.monthly": "1st working day",
            "ai.industries": ["Digital Payments", "Consumer Lending"],
            "reference_number": "CNK/PROP/T/52/26-27",
            "cnk.joint_partner.enabled": True,
            "cnk.joint_partner.name": "T. Partner",
            "cnk.joint_partner.short": "TN",
        },
        "industries": ["Digital Payments", "Consumer Lending"],
        "expect_fee": "Rs. 48,00,000",
        "expect_milestones": ["Rs.   1440000", "Rs.   1920000"],
        "weekly": "Weekly MONDAY",
        "phase4": True,
        "partner_short": "TN",
        "keep_partner_text": None,
        "industry_keywords": ["fintech", "payment", "lending", "transaction", "financial"],
    },
]

DOCX_CT = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def run_client_flow(client_fx):
    key = client_fx["key"]
    print(f"\n=== CLIENT: {key} ===", flush=True)
    inputs = full_inputs(**client_fx["overrides"])
    ctx_name = inputs["client.name"]
    client_context = {
        "name": ctx_name,
        "short_name": inputs["client.short_name"],
        "website": inputs["client.website"],
        "entities": inputs["client.entities"],
        "profile": inputs["client.profile"],
    }

    with transaction.atomic():
        row = TemplateMaster.objects.create(
            template_name=f"E2E {key}",
            config_path="documents/config_v2.yaml",
            template_path="documents/master_dpdpa_ia_v2.docx",
            is_active=True,
        )
        http = Client()

        # --- Endpoint 1: active list ---
        r = http.get("/templates/")
        check(f"{key}: GET /templates/ -> 200", r.status_code == 200, str(r.status_code))
        rows = r.json()
        check(
            f"{key}: list contains row w/ full shape",
            any(
                x["template_id"] == row.template_id
                and set(x) >= {"template_id", "template_name", "config_path", "template_path", "created_at"}
                for x in rows
            ),
            str(rows)[:200],
        )

        # --- Endpoint 2: schema ---
        r = http.get(f"/templates/{row.template_id}/schema/")
        check(f"{key}: GET schema -> 200", r.status_code == 200, str(r.status_code))
        schema = r.json()
        (SESSION / f"schema_{key}.json").write_text(json.dumps(schema, indent=2), encoding="utf-8")
        ai_sections = schema.get("ai_sections", [])
        check(f"{key}: schema has 3 ai_sections", len(ai_sections) == 3, str(len(ai_sections)))

        # --- Endpoint 4 (flow step 3): REAL AI generation per section ---
        ai_content = {}
        for sec in ai_sections:
            body = {
                "prompt": sec["prompt"],
                "output_schema": sec["output_schema"],
                "industries": client_fx["industries"],
                "client_context": client_context,
            }
            t0 = time.time()
            r = http.post("/ai/generate-section/", json.dumps(body), content_type="application/json")
            elapsed = time.time() - t0
            bid = sec["block_id"]
            check(
                f"{key}: AI {bid} ({sec['output_schema']}) -> 200",
                r.status_code == 200,
                f"status={r.status_code} body={str(r.content[:300])}",
            )
            if r.status_code == 200:
                payload = r.json()
                content = payload.get("content")
                ai_content[bid] = content
                print(f"    AI {bid}: {elapsed:.1f}s -> {json.dumps(content)[:180]}...", flush=True)
                if isinstance(content, str):
                    check(
                        f"{key}: AI {bid} no tool-debris",
                        "<tool_use" not in content and "<tool_name" not in content,
                        content[:200],
                    )
                    blob = content.lower()
                elif isinstance(content, list) and content and isinstance(content[0], dict):
                    blob = json.dumps(content).lower()
                    ok_shape = all(
                        isinstance(c, dict)
                        and c.get("id") and c.get("title") and c.get("summary")
                        and isinstance(c.get("bullets"), list) and c["bullets"]
                        for c in content
                    )
                    check(f"{key}: AI {bid} categories shape", ok_shape, str(content)[:200])
                    debris = blob.find("<tool_use")
                    check(f"{key}: AI {bid} no tool-debris", debris == -1, blob[debris:debris + 150])
                else:
                    blob = json.dumps(content).lower()
                    check(
                        f"{key}: AI {bid} bullets shape",
                        isinstance(content, list) and bool(content)
                        and all(isinstance(b, str) and b.strip() for b in content),
                        str(content)[:200],
                    )
                # industry-fit (loose any-of on profile text)
                if bid == "client_profile" and isinstance(content, str):
                    hit = any(k in content.lower() for k in client_fx["industry_keywords"])
                    check(f"{key}: AI profile industry-fit keyword", hit, content[:250])
            time.sleep(AI_SLEEP)

        (SESSION / f"ai_content_{key}.json").write_text(
            json.dumps(ai_content, indent=2), encoding="utf-8"
        )

        # --- Endpoint 3: preview (REAL render) ---
        body = {"inputs": inputs, "ai_content": ai_content}
        t0 = time.time()
        r = http.post(
            f"/templates/{row.template_id}/preview/",
            json.dumps(body),
            content_type="application/json",
        )
        elapsed = time.time() - t0
        check(
            f"{key}: POST preview -> 200 docx",
            r.status_code == 200 and r["Content-Type"] == DOCX_CT,
            f"status={r.status_code} ct={r.get('Content-Type')}",
        )
        if r.status_code != 200:
            print(f"    PREVIEW FAIL BODY: {r.content[:500]}", flush=True)
            return
        cd = r["Content-Disposition"]
        ref = inputs["reference_number"]
        check(f"{key}: filename has attachment+reference", "attachment" in cd and ref in cd, cd)
        docx = b"".join(r.streaming_content)
        print(f"    preview rendered {len(docx)} bytes in {elapsed:.1f}s", flush=True)
        (SESSION / f"preview_{key}.docx").write_bytes(docx)

        with zipfile.ZipFile(io.BytesIO(docx)) as z:
            names = set(z.namelist())
            doc_xml = z.read("word/document.xml")
            data2 = z.read("word/diagrams/data2.xml")
            data3 = z.read("word/diagrams/data3.xml")
        check(f"{key}: package has document+diagrams", {"word/document.xml", "word/diagrams/data2.xml", "word/diagrams/data3.xml"} <= names)
        doc_text = text_of(doc_xml)
        (SESSION / f"extracted_{key}.txt").write_text(doc_text, encoding="utf-8")

        # content assertions
        check(f"{key}: doc contains client name", ctx_name in doc_text)
        check(f"{key}: heading binds name", f"What is Personal Data for {ctx_name}" in doc_text)
        check(f"{key}: fee golden", client_fx["expect_fee"] in doc_text, client_fx["expect_fee"])
        for amt in client_fx["expect_milestones"]:
            check(f"{key}: milestone {amt}", amt in doc_text)
        check(f"{key}: ordinal date golden", "1st October ,2026" in doc_text)
        check(f"{key}: FY golden", "26-27" in doc_text)
        # AI content landed in the document
        prof = ai_content.get("client_profile") or ""
        if prof:
            probe = prof[:60].strip()
            check(f"{key}: profile text in doc", probe in doc_text, probe)
        cats = ai_content.get("categories") or []
        if cats:
            t0_ = cats[0]["title"]
            check(f"{key}: first category title in doc", t0_ in doc_text, t0_)
        bl = ai_content.get("processing_bullets") or []
        if bl:
            check(f"{key}: first processing bullet in doc", bl[0] in doc_text, bl[0])
        check(f"{key}: doc no tool-debris", "<tool_use" not in doc_text)
        # SmartArt data2
        d2 = data2.decode("utf-8", "replace")
        check(f"{key}: data2 client-name node", ctx_name in d2)
        for role in inputs["client.stakeholder_roles"]:
            check(f"{key}: data2 role {role}", role in d2)
        if client_fx["partner_short"]:
            check(f"{key}: data2 partner patched", f"{client_fx['partner_short']} PARTNER" in d2)
            check(f"{key}: data2 manager patched", f"{client_fx['partner_short']} MANAGER" in d2)
        if client_fx["keep_partner_text"]:
            check(
                f"{key}: data2 partner kept (disabled)",
                client_fx["keep_partner_text"] in d2 and "BJ PARTNER" not in d2 and "TN PARTNER" not in d2,
            )
        # data3 cadence
        d3 = data3.decode("utf-8", "replace")
        check(f"{key}: data3 weekly", client_fx["weekly"] in d3, client_fx["weekly"])
        # phase_4 gating
        p4_on = "Sustain / Operate" in doc_text
        check(f"{key}: phase_4 {'on' if client_fx['phase4'] else 'off'}", p4_on == client_fx["phase4"])
        if client_fx["phase4"]:
            check(f"{key}: phase_4 disclaimer", "This Phase is Optional" in doc_text)

    # transaction rolled back here
    check(f"{key}: registry row rolled back", not TemplateMaster.objects.filter(template_id=row.template_id).exists())


# ---------------------------------------------------------------------------
# Error-contract checks (live)
# ---------------------------------------------------------------------------
def run_error_contracts():
    print("\n=== ERROR CONTRACTS ===", flush=True)
    bad_yaml = SESSION / "bad_config.yaml"
    bad_yaml.write_text("version: 2\n", encoding="utf-8")

    with transaction.atomic():
        http = Client()
        # 404 unknown id
        r = http.get("/templates/999999/schema/")
        check("err: schema unknown -> 404", r.status_code == 404, str(r.status_code))
        # inactive row
        inactive = TemplateMaster.objects.create(
            template_name="E2E inactive", config_path="documents/config_v2.yaml",
            template_path="documents/master_dpdpa_ia_v2.docx", is_active=False,
        )
        r = http.get(f"/templates/{inactive.template_id}/schema/")
        check("err: schema inactive -> 404", r.status_code == 404, str(r.status_code))
        r = http.get("/templates/")
        check(
            "err: list excludes inactive",
            all(x["template_id"] != inactive.template_id for x in r.json()),
        )
        # bogus config path -> list excluded + schema 409
        bogus = TemplateMaster.objects.create(
            template_name="E2E bogus", config_path="documents/nope.yaml",
            template_path="documents/master_dpdpa_ia_v2.docx", is_active=True,
        )
        r = http.get("/templates/")
        check("err: list excludes missing-file row", all(x["template_id"] != bogus.template_id for x in r.json()))
        r = http.get(f"/templates/{bogus.template_id}/schema/")
        check(
            "err: schema missing config -> 409 code",
            r.status_code == 409 and r.json().get("code") == "config_file_missing",
            f"{r.status_code} {r.content[:120]}",
        )
        r = http.post(f"/templates/{bogus.template_id}/preview/", "{}", content_type="application/json")
        check("err: preview missing config -> 409", r.status_code == 409, str(r.status_code))
        # missing template file
        no_tpl = TemplateMaster.objects.create(
            template_name="E2E no-tpl", config_path="documents/config_v2.yaml",
            template_path="documents/ghost.docx", is_active=True,
        )
        r = http.get(f"/templates/{no_tpl.template_id}/schema/")
        check(
            "err: schema missing template -> 409 code",
            r.status_code == 409 and r.json().get("code") == "template_file_missing",
            f"{r.status_code} {r.content[:120]}",
        )
        # invalid config (valid yaml, bad structure)
        rel_bad = str(bad_yaml.relative_to(REPO)).replace("\\", "/")
        bad_row = TemplateMaster.objects.create(
            template_name="E2E bad-config", config_path=rel_bad,
            template_path="documents/master_dpdpa_ia_v2.docx", is_active=True,
        )
        r = http.get(f"/templates/{bad_row.template_id}/schema/")
        check(
            "err: schema invalid config -> 400 invalid_config",
            r.status_code == 400 and r.json().get("code") == "invalid_config",
            f"{r.status_code} {r.content[:150]}",
        )

        # preview contract errors against a valid row
        valid = TemplateMaster.objects.create(
            template_name="E2E err-valid", config_path="documents/config_v2.yaml",
            template_path="documents/master_dpdpa_ia_v2.docx", is_active=True,
        )
        base = full_inputs()
        base.pop("client_id", None)
        r = http.post(
            f"/templates/{valid.template_id}/preview/",
            json.dumps({"inputs": {"no_such_key": "x"}}),
            content_type="application/json",
        )
        check("err: preview unknown key -> 400", r.status_code == 400, f"{r.status_code} {r.content[:120]}")
        r = http.post(
            f"/templates/{valid.template_id}/preview/",
            json.dumps({"inputs": base}),
            content_type="application/json",
        )
        check(
            "err: preview w/o ai_content -> 400 missing_ai_content",
            r.status_code == 400 and r.json().get("code") == "missing_ai_content",
            f"{r.status_code} {r.content[:200]}",
        )
        bad_in = dict(base)
        bad_in["client.name"] = ""
        r = http.post(
            f"/templates/{valid.template_id}/preview/",
            json.dumps({"inputs": bad_in, "ai_content": {
                "client_profile": "x", "categories": [{"id": "a", "title": "b", "summary": "c", "bullets": ["d"]}],
                "processing_bullets": ["y"],
            }}),
            content_type="application/json",
        )
        check("err: preview required empty -> 400", r.status_code == 400, f"{r.status_code} {r.content[:150]}")
        bad_cats = dict(base)
        r = http.post(
            f"/templates/{valid.template_id}/preview/",
            json.dumps({"inputs": bad_cats, "ai_content": {
                "client_profile": "x", "categories": [{"id": "", "title": ""}],
                "processing_bullets": ["y"],
            }}),
            content_type="application/json",
        )
        check("err: preview malformed categories -> 400", r.status_code == 400, f"{r.status_code} {r.content[:150]}")

        # AI endpoint contract errors
        r = http.post("/ai/generate-section/", json.dumps({}), content_type="application/json")
        check("err: AI empty body -> 400", r.status_code == 400, str(r.status_code))
        r = http.post(
            "/ai/generate-section/",
            json.dumps({"prompt": "hi", "output_schema": "xml"}),
            content_type="application/json",
        )
        check("err: AI bad schema -> 400", r.status_code == 400, str(r.status_code))
        r = http.post(
            "/ai/generate-section/",
            json.dumps({"prompt": "Summarise {{ client.name }} for {{ reference_number }}.",
                        "output_schema": "text"}),
            content_type="application/json",
        )
        check(
            "err: AI unresolved vars -> 400 code",
            r.status_code == 400 and r.json().get("code") == "unresolved_prompt_vars",
            f"{r.status_code} {r.content[:150]}",
        )
        with mock.patch(
            "template_master.views.generate_section",
            side_effect=AIError("AI generation failed: forced"),
        ):
            r = http.post(
                "/ai/generate-section/",
                json.dumps({"prompt": "For {{ client.name }}.", "output_schema": "text",
                            "client_context": {"name": "X"}}),
                content_type="application/json",
            )
        check(
            "err: AI bridge failure -> 502 code",
            r.status_code == 502 and r.json().get("code") == "ai_generation_failed",
            f"{r.status_code} {r.content[:150]}",
        )
    TemplateMaster.objects.filter(template_name__startswith="E2E").delete()


# ---------------------------------------------------------------------------
def main():
    with transaction.atomic():
        # make sure no stale rows interfere
        pass
    TemplateMaster.objects.filter(template_name__startswith="E2E").delete()
    for fx in CLIENTS:
        run_client_flow(fx)
    run_error_contracts()

    fails = [r for r in RESULTS if r[1] == "FAIL"]
    print(f"\n=== SUMMARY: {len(RESULTS)} checks, {len(fails)} FAIL ===", flush=True)
    lines = ["# E2E Results", "", f"Total checks: {len(RESULTS)}; FAIL: {len(fails)}", ""]
    for name, status, detail in RESULTS:
        lines.append(f"- [{status}] {name}" + (f"  -- {detail}" if detail and status == "FAIL" else ""))
    (SESSION / "results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    if fails:
        sys.exit(1)


if __name__ == "__main__":
    main()
