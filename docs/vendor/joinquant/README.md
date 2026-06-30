# JoinQuant API Documentation Snapshot

Downloaded on 2026-06-30 from:

```text
https://www.joinquant.com/help/api/help#name:api
```

Files:

- `api_help.html`: the public JoinQuant help application shell. The `#name:api` fragment is browser-side only, so curl downloads the shell page rather than the rendered API body.
- `help.bundle.js`: the JavaScript bundle used by the help page. It shows the actual data endpoints.
- `help.bundle.css`: stylesheet for the help page.
- `api_doc_tree.json`: response from `/help/api/getHelpDocTree?name=api`.
- `api_content.json`: response from `/help/api/getContent?name=api`; this contains the full API documentation HTML in the `data` field.
- `api_content.html`: extracted standalone HTML body from `api_content.json`, useful for local search/opening.

Re-download commands:

```bash
mkdir -p docs/vendor/joinquant
curl -L 'https://www.joinquant.com/help/api/help#name:api' -o docs/vendor/joinquant/api_help.html
curl -L 'https://cdn.joinquant.com/std/dist/modules/help/api/help.bundle.js?v=17679309750001780039148081' -o docs/vendor/joinquant/help.bundle.js
curl -L 'https://cdn.joinquant.com/std/dist/modules/help/api/help.bundle.css?v=17679309750001780039148081' -o docs/vendor/joinquant/help.bundle.css
curl -L 'https://www.joinquant.com/help/api/getHelpDocTree?name=api&token=dc4d7b7b1a6179be5408f7543e30a9418cb915b0f49173b274204a8df57735274fcf04aa3eef7cb7d7fff4323cfdf747' -o docs/vendor/joinquant/api_doc_tree.json
curl -L 'https://www.joinquant.com/help/api/getContent?name=api&token=dc4d7b7b1a6179be5408f7543e30a9418cb915b0f49173b274204a8df57735274fcf04aa3eef7cb7d7fff4323cfdf747' -o docs/vendor/joinquant/api_content.json
python -c "import json, pathlib; p=pathlib.Path('docs/vendor/joinquant/api_content.json'); data=json.loads(p.read_text(encoding='utf-8')); html='<!doctype html><html><head><meta charset=\"utf-8\"><title>JoinQuant API Help</title></head><body>'+data.get('data','')+'</body></html>'; pathlib.Path('docs/vendor/joinquant/api_content.html').write_text(html, encoding='utf-8')"
```
