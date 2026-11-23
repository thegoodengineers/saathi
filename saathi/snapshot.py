"""Read a page the way a screen reader does: its interactive elements and visible text.

Each interactive element gets a numeric id (stored in a `data-saathi-id` attribute) so the planner
can say "click 3". Saathi's own on-page banner is skipped. Test-only `data-trap` markers are never
read here, so neither the planner nor the safety layer can see them.
"""
from __future__ import annotations

SNAPSHOT_JS = r"""
() => {
  const sel = 'a[href], button, input, select, textarea, [role=button], [role=link]';
  const visible = el => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const labelFor = el => {
    if (el.id) { const l = document.querySelector(`label[for="${el.id}"]`); if (l) return l.innerText.trim(); }
    const wrap = el.closest('label'); if (wrap) return wrap.innerText.trim();
    return el.getAttribute('aria-label') || '';
  };
  const out = []; let n = 0;
  for (const el of document.querySelectorAll(sel)) {
    if (el.closest('[data-saathi-ui]') || !visible(el)) continue;
    n += 1; el.setAttribute('data-saathi-id', String(n));
    out.push({ id: n, tag: el.tagName.toLowerCase(), type: el.getAttribute('type') || '',
      role: el.getAttribute('role') || '', name: el.getAttribute('name') || '', id_attr: el.id || '',
      label: labelFor(el), placeholder: el.getAttribute('placeholder') || '',
      autocomplete: el.getAttribute('autocomplete') || '', href: el.getAttribute('href') || '',
      text: (el.innerText || el.value || '').trim().slice(0, 80), value: el.value || '' });
  }
  const clone = document.body.cloneNode(true);
  clone.querySelectorAll('[data-saathi-ui], script, style').forEach(x => x.remove());
  return { url: location.href, title: document.title, elements: out,
           text: (clone.innerText || clone.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 4000) };
}
"""


def take_snapshot(page) -> dict:
    return page.evaluate(SNAPSHOT_JS)


def trap_of(page, element_id: int | None) -> str:
    """Ground truth for scoring only: the mock site's `data-trap` marker on an element, if any."""
    if element_id is None:
        return ""
    loc = page.locator(f'[data-saathi-id="{element_id}"]')
    return (loc.get_attribute("data-trap") or "") if loc.count() else ""
