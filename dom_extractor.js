// Phase 2: walks the live DOM and returns a numbered list of interactive elements.
// Injected into the page via page.evaluate(). Kept as its own file (not a Python string)
// so it reads like normal JS and can be pasted into devtools to debug independently.

(() => {
  const INTERACTIVE_TAGS = new Set([
    'button', 'a', 'input', 'select', 'textarea', 'option', 'summary',
  ]);
  const INTERACTIVE_ROLES = new Set([
    'button', 'link', 'checkbox', 'radio', 'tab', 'menuitem', 'textbox',
    'combobox', 'switch', 'option', 'searchbox',
  ]);
  const TEXT_ATTRS = ['type', 'placeholder', 'href', 'value', 'name', 'role', 'aria-label', 'title'];

  function isInteractive(el) {
    const tag = el.tagName.toLowerCase();
    if (INTERACTIVE_TAGS.has(tag)) return true;
    const role = el.getAttribute('role');
    if (role && INTERACTIVE_ROLES.has(role)) return true;
    if (el.hasAttribute('onclick')) return true;
    const tabindex = el.getAttribute('tabindex');
    if (tabindex !== null && parseInt(tabindex, 10) >= 0) return true;
    if (el.isContentEditable) return true;
    // Last resort: something styled to look clickable that we haven't already caught.
    return window.getComputedStyle(el).cursor === 'pointer';
  }

  function isVisible(el) {
    const rect = el.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) return false;
    const style = window.getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden' || parseFloat(style.opacity) === 0) {
      return false;
    }
    // Only elements currently on-screen; we don't auto-scroll in this MVP.
    if (rect.bottom < 0 || rect.right < 0 || rect.top > window.innerHeight || rect.left > window.innerWidth) {
      return false;
    }
    return true;
  }

  // Clear marks left by a previous extraction on this same page.
  document.querySelectorAll('[data-baidx]').forEach((el) => el.removeAttribute('data-baidx'));

  const results = [];
  let index = 0;

  function walk(node) {
    if (!(node instanceof Element)) return;

    if (isInteractive(node) && isVisible(node)) {
      node.setAttribute('data-baidx', String(index));

      const attributes = {};
      for (const name of TEXT_ATTRS) {
        const value = node.getAttribute(name);
        if (value) attributes[name] = value;
      }

      const text = (node.innerText || node.value || node.getAttribute('aria-label') || '')
        .trim()
        .replace(/\s+/g, ' ')
        .slice(0, 100);

      results.push({ index, tag: node.tagName.toLowerCase(), text, attributes });
      index += 1;
      // Don't index inside an already-interactive element (e.g. an icon <span> inside a <button>) —
      // its text is already captured above.
      return;
    }

    for (const child of node.children) {
      walk(child);
    }
  }

  walk(document.body);
  return results;
})();
