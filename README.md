# Personal publications site

Dynamically editable, statically generated personal publications site.
You edit a single data file → static HTML with citation (`citation_*`)
meta tags is generated → it is hosted for free on GitHub Pages.

**Author:** krse

## Why this way

Academic indexing crawlers do **not** run JavaScript reliably. An SPA
(React/Vue) would break indexing. The solution: **dynamic to edit, static to
serve.** The citation meta tags live in the finished HTML, exactly as indexers
want.

## Files

| file | what it is |
|---|---|
| `publications.toml` | **The only file you work in.** Paper data + settings. |
| `build.py` | The generator. Pure Python 3.11+ stdlib, no dependencies. |
| `templates/` | HTML templates (index + publication page). |
| `assets/style.css` | Styles. |
| `dist/` | **Generated site.** Not edited by hand — don't touch it. |

## Add / edit / remove a publication

1. Open `publications.toml`.
2. Copy a `[[publication]]` block and change the values (or edit/delete an
   existing one). Key fields: `pdf_url` (direct Zenodo PDF URL — **critical for
   indexing**), `doi`, `repo_url` (GitHub repo with Jupyter/Python/C++),
   `abstract`, `keywords`.
3. Run `python3 build.py`.
4. Push. The GitHub Action rebuilds and deploys.

## First run

```bash
python3 build.py          # generates dist/
# local preview:
python3 -m http.server -d dist 8000   # then open http://localhost:8000
```

In `publications.toml`, set `base_url` to your GitHub username
(`https://<username>.github.io`).

## Deployment (user-site: `username.github.io`)

This directory **is** the repository — only the site goes to GitHub, nothing
else (no PDFs, LaTeX, figures).

1. The repo must be named **`<username>.github.io`**.
2. From this directory: `git init`, commit, push to `main`.
3. Repo → Settings → Pages → **Source = GitHub Actions**.
4. The workflow `.github/workflows/deploy.yml` builds `dist/` and deploys it.
   The site goes live at `https://<username>.github.io/`.

## Indexing

The generated `citation_*` meta tags (Highwire / Dublin Core) are read by
several academic indexers, not just one:

- **Semantic Scholar**, **OpenAlex**, **CORE**, **BASE**, **Scilit**,
  **Lens.org** — all crawl public pages with valid citation tags on their own
  (usually weeks after deployment).

Notes:

- `citation_pdf_url` must point to a public, text-searchable PDF (a Zenodo PDF
  qualifies). Without it indexers won't pick up the full text — `build.py`
  warns you when it's missing.
- Because each paper has a **Zenodo DOI**, its metadata also propagates
  automatically through **DataCite** (and **OAI-PMH**), which OpenAlex, CORE
  and BASE ingest directly — independent of this site being crawled.
- Link your **ORCID** in `publications.toml` so records attach to your profile
  across these systems.

## License

MIT — see [`LICENSE`](LICENSE).
