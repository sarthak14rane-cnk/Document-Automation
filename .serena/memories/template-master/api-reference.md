# template_master — endpoints, inputs, outputs (verified live 2026-10-30)

Base: http://127.0.0.1:8765 (root-mounted). All unauthenticated (AllowAny). Source:
template_master/{urls,views,serializers,exceptions}.py + engine/schema_builder.py.

## GET /templates/
Active rows (is_active AND both files exist; missing-file rows silently skipped, logged
TEMPLATE_SKIPPED_FILE_MISSING). 200 JSON array:
[{template_id, template_name, config_path, template_path, created_at}]. Always 200.

## GET /templates/{id}/schema/
200 JSON {template:{template_id,template_name,service,display_name,version}, groups:[{group,title,
fields:[{key,label,type,required,default,hint,options,enabled_when,items,meta,validation,
default_from}]}], base_fields:[service,version,client_id,created_by], ai_sections:[{section_id,
block_id,label,type,output_schema,editable,grounding,prompt(raw Jinja),requires[]}]}.
block_id is the key used in preview ai_content; output_schema feeds /ai/generate-section/.
Errors: 404 not_found; 409 config_file_missing|template_file_missing; 400 invalid_config.

## POST /templates/{id}/preview/
Body {inputs(required dict), ai_content(optional dict, block_id->content)}. Renders + streams
.docx (FileResponse — READ VIA streaming_content, NOT .content). Content-Type docx;
Content-Disposition attachment slug_filename.docx.
ai_content shape: text->str; bullets->str[]; categories->[{id,title,summary,bullets:[]}].
Success 200 docx. Errors: 404 not_found; 409 config/template_file_missing; 400 invalid_config |
{detail,code:missing_ai_content,blocks:[...]} | input-validation array; 500 render_failed.

## POST /ai/generate-section/
Body {prompt(raw Jinja, required), output_schema(text|bullets|categories, required),
industries?[], client_context?{name,short_name,website,entities,profile}, model_id?str}.
Server renders prompt strict (undefined -> 400 unresolved_prompt_vars w/ variables list).
Prompt vars: client.*, ai.industries, ai.industries_phrase, computed.entities_phrase.
200 {output_schema, content}. content shape per schema (str / str[] / categories[]).
Errors: 400 field-validation + unresolved_prompt_vars; 502 {detail,code:ai_generation_failed}
(retryable).