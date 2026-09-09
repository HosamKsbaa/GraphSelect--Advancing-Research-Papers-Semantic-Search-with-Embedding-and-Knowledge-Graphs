/**
 * ALRS v2 Interactive Presentation Client Controller
 * Provides keyboard navigation, notes drawer synchronization, overview grid,
 * dark/light theme switching, URL hash deep linking, and offline Mermaid rendering.
 */

(function () {
  'use strict';

  let currentSlide = 1;
  let totalSlides = 1;
  let slides = [];

  function initPresentation() {
    slides = Array.from(document.querySelectorAll('.slide'));
    totalSlides = slides.length || 1;

    const totalEl = document.getElementById('slide-num-total');
    if (totalEl) totalEl.textContent = totalSlides.toString().padStart(2, '0');

    // Parse URL hash on initial load (e.g., #slide-3)
    const hashMatch = window.location.hash.match(/#slide-(\d+)/);
    if (hashMatch) {
      const target = parseInt(hashMatch[1], 10);
      if (target >= 1 && target <= totalSlides) {
        currentSlide = target;
      }
    }

    bindControls();
    updateSlide();
  }

  function updateSlide() {
    slides.forEach((slide, idx) => {
      const slideNum = idx + 1;
      slide.classList.remove('active', 'prev');
      if (slideNum === currentSlide) {
        slide.classList.add('active');
      } else if (slideNum < currentSlide) {
        slide.classList.add('prev');
      }
    });

    // Update Header Counter & Title
    const curEl = document.getElementById('slide-num-current');
    if (curEl) curEl.textContent = currentSlide.toString().padStart(2, '0');

    const activeSlide = slides[currentSlide - 1];
    if (activeSlide) {
      const titleEl = document.getElementById('header-slide-title');
      const slideHeading = activeSlide.querySelector('.slide-title, .slide-heading, h1, h2');
      if (titleEl && slideHeading) {
        titleEl.textContent = slideHeading.textContent.trim();
      }
      syncPresenterNotes(activeSlide);
      renderMermaidInSlide(activeSlide);
    }

    // Update Progress Bar
    const progressFill = document.getElementById('progress-fill');
    if (progressFill && totalSlides > 0) {
      const pct = (currentSlide / totalSlides) * 100;
      progressFill.style.width = pct + '%';
    }

    // Sync URL Hash
    if (history.replaceState) {
      history.replaceState(null, '', '#slide-' + currentSlide);
    } else {
      window.location.hash = '#slide-' + currentSlide;
    }
  }

  function nextSlide() {
    if (currentSlide < totalSlides) {
      currentSlide++;
      updateSlide();
    }
  }

  function prevSlide() {
    if (currentSlide > 1) {
      currentSlide--;
      updateSlide();
    }
  }

  function goToSlide(num) {
    if (num >= 1 && num <= totalSlides) {
      currentSlide = num;
      updateSlide();
      closeOverview();
    }
  }

  function syncPresenterNotes(activeSlide) {
    const rawNotes = activeSlide.querySelector('.slide-notes-data');
    const container = document.getElementById('notes-content') || document.getElementById('presenter-content');
    if (!container) return;

    if (rawNotes) {
      container.innerHTML = rawNotes.innerHTML;
    } else {
      const title = activeSlide.querySelector('.slide-title, .slide-heading')?.textContent || 'Slide';
      container.innerHTML = `<h4>Talking Points</h4><ul><li>Discuss ${title}.</li><li>Address empirical results and baseline comparisons.</li></ul>`;
    }
  }

  function togglePresenterNotes() {
    const drawer = document.getElementById('notes-drawer') || document.getElementById('presenter-drawer');
    if (!drawer) return;
    const isOpen = drawer.classList.toggle('open');
    const btn = document.getElementById('btn-notes-toggle');
    if (btn) btn.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
  }

  function toggleOverview() {
    const modal = document.getElementById('overview-modal');
    if (!modal) return;
    const isOpen = modal.classList.toggle('open');
    const btn = document.getElementById('btn-overview-toggle');
    if (btn) btn.setAttribute('aria-expanded', isOpen ? 'true' : 'false');

    if (isOpen) {
      renderOverviewGrid();
      const activeThumb = modal.querySelector('.overview-thumb.active') || modal.querySelector('.overview-thumb');
      if (activeThumb) activeThumb.focus();
    } else if (btn) {
      btn.focus();
    }
  }

  function closeOverview(event) {
    if (!event || event.target.id === 'overview-modal') {
      const modal = document.getElementById('overview-modal');
      if (modal) modal.classList.remove('open');
      const btn = document.getElementById('btn-overview-toggle');
      if (btn) {
        btn.setAttribute('aria-expanded', 'false');
        btn.focus();
      }
    }
  }

  function renderOverviewGrid() {
    const grid = document.getElementById('overview-grid');
    if (!grid) return;
    grid.innerHTML = '';

    slides.forEach((slide, idx) => {
      const num = idx + 1;
      const heading = slide.querySelector('.slide-title, .slide-heading, h1, h2')?.textContent || `Slide ${num}`;
      const thumb = document.createElement('div');
      thumb.className = `overview-thumb ${num === currentSlide ? 'active' : ''}`;
      thumb.setAttribute('tabindex', '0');
      thumb.setAttribute('role', 'button');
      thumb.setAttribute('aria-label', `Slide ${num}: ${heading}`);
      thumb.innerHTML = `
        <div class="ot-num">Slide ${num.toString().padStart(2, '0')}</div>
        <div class="ot-title">${heading}</div>
        <div style="font-size: 0.75rem; color: #64748b; margin-top: 4px;">Click to jump</div>
      `;
      thumb.onclick = () => goToSlide(num);
      thumb.onkeydown = (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          goToSlide(num);
        }
      };
      grid.appendChild(thumb);
    });
  }

  function toggleTheme() {
    const body = document.body;
    const isLight = body.classList.toggle('light-theme');
    body.setAttribute('data-theme', isLight ? 'light' : 'dark');
    const btn = document.getElementById('btn-theme-toggle');
    if (btn) {
      btn.textContent = isLight ? '🌙 Dark' : '☀️ Light';
    }
  }

  function toggleFullscreen() {
    const doc = document;
    const el = document.documentElement;
    if (!doc.fullscreenElement) {
      if (el.requestFullscreen) el.requestFullscreen().catch(() => {});
    } else {
      if (doc.exitFullscreen) doc.exitFullscreen().catch(() => {});
    }
  }

  function renderMermaidInSlide(slide) {
    if (typeof window.mermaid !== 'undefined') {
      const mermaidNodes = slide.querySelectorAll('.mermaid:not([data-processed="true"])');
      if (mermaidNodes.length > 0) {
        window.mermaid.run({ nodes: mermaidNodes }).catch(() => {});
      }
    }
  }

  function bindControls() {
    const prevBtn = document.getElementById('btn-prev');
    if (prevBtn) prevBtn.onclick = prevSlide;

    const nextBtn = document.getElementById('btn-next');
    if (nextBtn) nextBtn.onclick = nextSlide;

    const notesBtn = document.getElementById('btn-notes-toggle');
    if (notesBtn) notesBtn.onclick = togglePresenterNotes;

    const overviewBtn = document.getElementById('btn-overview-toggle');
    if (overviewBtn) overviewBtn.onclick = toggleOverview;

    const themeBtn = document.getElementById('btn-theme-toggle');
    if (themeBtn) themeBtn.onclick = toggleTheme;

    const fsBtn = document.getElementById('btn-fullscreen-toggle');
    if (fsBtn) fsBtn.onclick = toggleFullscreen;

    const modal = document.getElementById('overview-modal');
    if (modal) modal.onclick = closeOverview;

    window.addEventListener('hashchange', () => {
      const match = window.location.hash.match(/#slide-(\d+)/);
      if (match) {
        const target = parseInt(match[1], 10);
        if (target >= 1 && target <= totalSlides && target !== currentSlide) {
          goToSlide(target);
        }
      }
    });

    document.addEventListener('keydown', handleKeyNavigation);
  }

  function handleKeyNavigation(e) {
    if (['input', 'textarea'].includes(e.target.tagName.toLowerCase())) return;

    const modal = document.getElementById('overview-modal');
    const isModalOpen = modal && modal.classList.contains('open');

    if (isModalOpen) {
      if (e.key === 'Escape') {
        e.preventDefault();
        toggleOverview();
      }
      return;
    }

    const isInteractive = ['button', 'select'].includes(e.target.tagName.toLowerCase()) ||
                          e.target.closest('button') ||
                          e.target.closest('[role="button"]') ||
                          e.target.closest('a');

    if (e.key === ' ' && isInteractive) return;

    switch (e.key) {
      case 'ArrowRight':
      case ' ':
      case 'PageDown':
      case 'j':
      case 'J':
        e.preventDefault();
        nextSlide();
        break;
      case 'ArrowLeft':
      case 'PageUp':
      case 'k':
      case 'K':
        e.preventDefault();
        prevSlide();
        break;
      case 'Home':
        e.preventDefault();
        goToSlide(1);
        break;
      case 'End':
        e.preventDefault();
        goToSlide(totalSlides);
        break;
      case 'p':
      case 'P':
        e.preventDefault();
        togglePresenterNotes();
        break;
      case 'o':
      case 'O':
      case 'm':
      case 'M':
        e.preventDefault();
        toggleOverview();
        break;
      case 't':
      case 'T':
        e.preventDefault();
        toggleTheme();
        break;
      case 'f':
      case 'F':
        e.preventDefault();
        toggleFullscreen();
        break;
      case 'Escape':
        const drawer = document.getElementById('notes-drawer') || document.getElementById('presenter-drawer');
        if (drawer) drawer.classList.remove('open');
        const ntBtn = document.getElementById('btn-notes-toggle');
        if (ntBtn) ntBtn.setAttribute('aria-expanded', 'false');
        if (modal) modal.classList.remove('open');
        const ovBtn = document.getElementById('btn-overview-toggle');
        if (ovBtn) ovBtn.setAttribute('aria-expanded', 'false');
        break;
    }
  }

  // Export functions to window for onclick handlers
  window.nextSlide = nextSlide;
  window.prevSlide = prevSlide;
  window.goToSlide = goToSlide;
  window.togglePresenterNotes = togglePresenterNotes;
  window.toggleOverview = toggleOverview;
  window.closeOverview = closeOverview;
  window.toggleTheme = toggleTheme;
  window.toggleFullscreen = toggleFullscreen;

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initPresentation);
  } else {
    initPresentation();
  }
})();
