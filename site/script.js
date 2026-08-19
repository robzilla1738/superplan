const header = document.querySelector("[data-header]");
const flowSteps = Array.from(document.querySelectorAll("[data-flow-steps] li"));
const deckSlides = Array.from(document.querySelectorAll(".deck-slide"));
const deckRailItems = Array.from(document.querySelectorAll(".deck-rail span"));
const tabButtons = Array.from(document.querySelectorAll("[data-tab]"));
const tabPanels = Array.from(document.querySelectorAll("[data-panel]"));
const copyButtons = Array.from(document.querySelectorAll("[data-copy]"));

function setScrolledHeader() {
  header?.classList.toggle("is-scrolled", window.scrollY > 8);
}

function setActiveStep() {
  if (!flowSteps.length) return;
  const progress = Math.min(1, Math.max(0, (window.scrollY - 380) / 820));
  const activeIndex = Math.min(flowSteps.length - 1, Math.floor(progress * flowSteps.length));
  flowSteps.forEach((step, index) => {
    step.classList.toggle("is-active", index === activeIndex);
  });
}

function setActiveDeckSlide() {
  if (!deckSlides.length) return;

  let activeIndex = 0;
  let bestDistance = Number.POSITIVE_INFINITY;

  deckSlides.forEach((slide, index) => {
    const rect = slide.getBoundingClientRect();
    const distance = Math.abs(rect.top - window.innerHeight * 0.32);
    if (distance < bestDistance) {
      bestDistance = distance;
      activeIndex = index;
    }
  });

  deckSlides.forEach((slide, index) => {
    slide.classList.toggle("is-active", index === activeIndex);
  });
  deckRailItems.forEach((item, index) => {
    item.classList.toggle("is-active", index === activeIndex);
  });
}

function selectTab(tabName) {
  tabButtons.forEach((button) => {
    const isActive = button.dataset.tab === tabName;
    button.classList.toggle("is-active", isActive);
    button.setAttribute("aria-selected", String(isActive));
  });

  tabPanels.forEach((panel) => {
    const isActive = panel.dataset.panel === tabName;
    panel.classList.toggle("is-active", isActive);
    panel.toggleAttribute("hidden", !isActive);
  });
}

tabButtons.forEach((button) => {
  button.addEventListener("click", () => selectTab(button.dataset.tab));
});

copyButtons.forEach((button) => {
  button.addEventListener("click", async () => {
    const target = document.querySelector(button.dataset.copy);
    const text = target?.innerText.trim();
    if (!text) return;

    try {
      await navigator.clipboard.writeText(text);
      const original = button.textContent.trim();
      button.lastChild.textContent = "Copied";
      window.setTimeout(() => {
        button.lastChild.textContent = original;
      }, 1400);
    } catch {
      button.lastChild.textContent = "Select text";
    }
  });
});

window.addEventListener("scroll", () => {
  setScrolledHeader();
  setActiveStep();
  setActiveDeckSlide();
}, { passive: true });

setScrolledHeader();
setActiveStep();
setActiveDeckSlide();
