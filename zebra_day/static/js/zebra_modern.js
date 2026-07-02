/**
 * Zebra Day Modern UI - JavaScript Utilities
 */

// Global state
const ZebraDay = {
    config: window.ZebraConfig || {},
    toasts: [],
};

// DOM Ready
document.addEventListener('DOMContentLoaded', function() {
    initMobileMenu();
    initTooltips();
});

// Mobile Menu Toggle
function initMobileMenu() {
    const menuToggle = document.getElementById('menu-toggle');
    const navLinks = document.getElementById('nav-links');
    
    if (menuToggle && navLinks) {
        menuToggle.addEventListener('click', () => {
            navLinks.classList.toggle('active');
        });
    }
}

// Tooltips
function initTooltips() {
    document.querySelectorAll('[title]').forEach(el => {
        el.addEventListener('mouseenter', showTooltip);
        el.addEventListener('mouseleave', hideTooltip);
    });
}

function showTooltip(e) {
    const title = e.target.getAttribute('title');
    if (!title) return;
    
    e.target.setAttribute('data-title', title);
    e.target.removeAttribute('title');
    
    const tooltip = document.createElement('div');
    tooltip.className = 'tooltip';
    tooltip.textContent = title;
    tooltip.style.cssText = `
        position: fixed;
        background: var(--color-gray-700, #1f1f1f);
        color: white;
        padding: 6px 10px;
        border-radius: 6px;
        font-size: 12px;
        max-width: 280px;
        z-index: 9999;
        pointer-events: none;
    `;
    
    document.body.appendChild(tooltip);
    
    const rect = e.target.getBoundingClientRect();
    const margin = 8;
    let left = rect.left + (rect.width / 2) - (tooltip.offsetWidth / 2);
    let top = rect.top - tooltip.offsetHeight - margin;
    
    left = Math.max(margin, Math.min(left, window.innerWidth - tooltip.offsetWidth - margin));
    if (top < margin) top = rect.bottom + margin;
    
    tooltip.style.left = left + 'px';
    tooltip.style.top = top + 'px';
    
    e.target._tooltip = tooltip;
}

function hideTooltip(e) {
    const title = e.target.getAttribute('data-title');
    if (title) {
        e.target.setAttribute('title', title);
        e.target.removeAttribute('data-title');
    }
    if (e.target._tooltip) {
        e.target._tooltip.remove();
        delete e.target._tooltip;
    }
}

// Toast Notifications
function showToast(type, title, message, duration = 5000) {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const icons = {
        success: 'fa-check-circle',
        error: 'fa-exclamation-circle',
        warning: 'fa-exclamation-triangle',
        info: 'fa-info-circle'
    };

    const toastType = Object.prototype.hasOwnProperty.call(icons, type) ? type : 'info';
    const toast = document.createElement('div');
    toast.className = `toast toast-${toastType}`;

    const iconWrap = document.createElement('div');
    iconWrap.className = 'toast-icon';
    const icon = document.createElement('i');
    icon.className = `fas ${icons[toastType]}`;
    iconWrap.appendChild(icon);

    const content = document.createElement('div');
    content.className = 'toast-content';
    const titleEl = document.createElement('div');
    titleEl.className = 'toast-title';
    titleEl.textContent = title;
    const messageEl = document.createElement('div');
    messageEl.className = 'toast-message';
    messageEl.textContent = message;
    content.appendChild(titleEl);
    content.appendChild(messageEl);

    const close = document.createElement('button');
    close.className = 'toast-close';
    close.type = 'button';
    close.setAttribute('aria-label', 'Close notification');
    close.textContent = 'x';
    close.addEventListener('click', () => toast.remove());

    toast.appendChild(iconWrap);
    toast.appendChild(content);
    toast.appendChild(close);

    container.appendChild(toast);

    if (duration > 0) {
        setTimeout(() => toast.remove(), duration);
    }

    return toast;
}

// Loading Overlay
function showLoading(message = 'Loading...') {
    const overlay = document.getElementById('loading-overlay');
    if (overlay) {
        const p = document.getElementById('loading-message') || overlay.querySelector('p');
        if (p) p.textContent = message;
        overlay.classList.remove('d-none');
    }
}

function hideLoading() {
    const overlay = document.getElementById('loading-overlay');
    if (overlay) {
        overlay.classList.add('d-none');
    }
}

// Network Scan (SSE)
window.__zdayNetworkScan = window.__zdayNetworkScan || {
    source: null,
    scanId: null,
    lab: null,
};

function _scanEls() {
    return {
        progress: document.getElementById('scan-progress'),
        counter: document.getElementById('scan-progress-counter'),
        current: document.getElementById('scan-current-ip'),
        list: document.getElementById('scan-ip-list'),
        cancelBtn: document.getElementById('scan-cancel-btn'),
    };
}

function _resetScanOverlay() {
    const els = _scanEls();
    if (els.counter) els.counter.textContent = 'Checked 0/255';
    if (els.current) els.current.innerHTML = '';
    if (els.list) els.list.innerHTML = '';
    if (els.cancelBtn) {
        els.cancelBtn.disabled = true;
    }
}

function showNetworkScanOverlay(message) {
    showLoading(message || 'Scanning network for Zebra printers...');
    const els = _scanEls();
    if (els.progress) els.progress.classList.remove('d-none');
    _resetScanOverlay();
}

function hideNetworkScanOverlay() {
    const els = _scanEls();
    if (els.progress) els.progress.classList.add('d-none');
    hideLoading();
}

function startNetworkScan(event, formEl) {
    // Progressive enhancement: if SSE/EventSource isn't available, let the form submit normally.
    if (!window.EventSource) {
        return true;
    }
    if (event) event.preventDefault();

    const formData = new FormData(formEl);
    const ipStub = (formData.get('ip_stub') || '192.168.1').toString().trim();
    const scanWait = (formData.get('scan_wait') || '0.5').toString().trim();
    const lab = (formData.get('lab') || 'scan-results').toString().trim();

    startNetworkScanWithParams(ipStub, scanWait, lab);
    return false;
}

function startNetworkScanWithParams(ipStub, scanWait, lab, scanHttpPort) {
    // Close any existing scan stream
    if (window.__zdayNetworkScan.source) {
        try { window.__zdayNetworkScan.source.close(); } catch (_) {}
    }
    window.__zdayNetworkScan.source = null;
    window.__zdayNetworkScan.scanId = null;
    window.__zdayNetworkScan.lab = lab;

    showNetworkScanOverlay('Scanning network for Zebra printers...');

    const els = _scanEls();
    if (els.cancelBtn) {
        els.cancelBtn.onclick = async function () {
            const scanId = window.__zdayNetworkScan.scanId;
            if (!scanId) return;
            els.cancelBtn.disabled = true;
            try {
                const url = `/config/scan/cancel?scan_id=${encodeURIComponent(scanId)}`;
                const resp = await fetch(url, { method: 'POST' });
                if (!resp.ok) {
                    throw new Error(`Cancel failed (${resp.status})`);
                }
                showToast('info', 'Scan Cancelled', 'Stopping scan and saving partial results...');
            } catch (e) {
                showToast('error', 'Cancel Failed', e?.message || 'Cancel request failed');
                els.cancelBtn.disabled = false;
            }
        };
    }

    const params = new URLSearchParams({
        ip_stub: ipStub,
        scan_wait: scanWait,
        lab: lab,
    });
    if (scanHttpPort) {
        params.set('scan_http_port', scanHttpPort);
    }

    const source = new EventSource(`/config/scan/stream?${params.toString()}`);
    window.__zdayNetworkScan.source = source;

    source.onmessage = function (evt) {
        let msg;
        try {
            msg = JSON.parse(evt.data);
        } catch (_) {
            return;
        }

        const kind = msg.kind;
        if (kind === 'init') {
            window.__zdayNetworkScan.scanId = msg.scan_id;
            if (els.cancelBtn) els.cancelBtn.disabled = false;
            if (els.counter && msg.total) {
                els.counter.textContent = `Checked 0/${msg.total}`;
            }
            return;
        }

        if (kind === 'checking') {
            if (els.current) {
                els.current.innerHTML = `<i class="fas fa-spinner fa-spin"></i> Scanning <strong>${msg.ip}</strong>`;
            }
            return;
        }

        if (kind === 'checked') {
            if (els.counter) {
                els.counter.textContent = `Checked ${msg.checked}/${msg.total}`;
            }
            if (els.list) {
                const row = document.createElement('div');
                row.className = 'scan-ip-row';
                const meta = msg.open ? `open:${msg.source || 'printer'}` : 'closed';
                row.innerHTML = `<span class="scan-ip">${msg.ip}</span><span class="scan-ip-meta">${meta}</span>`;
                els.list.appendChild(row);
                els.list.scrollTop = els.list.scrollHeight;
            }
            return;
        }

        if (kind === 'found') {
            showToast('success', 'Printer Found', `${msg.ip} (${msg.model || 'Unknown'})`);
            return;
        }

        if (kind === 'error') {
            showToast('error', 'Scan Error', msg.message || 'Unknown scan error');
            try { source.close(); } catch (_) {}
            hideNetworkScanOverlay();
            return;
        }

        if (kind === 'done') {
            if (els.current) {
                const verb = msg.cancelled ? 'Cancelled' : 'Completed';
                els.current.textContent = `${verb}. Redirecting...`;
            }
            if (els.cancelBtn) els.cancelBtn.disabled = true;
            try { source.close(); } catch (_) {}

            // Redirect to results lab page (partial results are already saved).
            const targetLab = window.__zdayNetworkScan.lab || lab;
            setTimeout(() => {
                window.location.href = `/printers/${encodeURIComponent(targetLab)}`;
            }, 400);
        }
    };

    source.onerror = function () {
        // Let normal completion happen if it was a clean shutdown.
        showToast('error', 'Scan Connection Lost', 'Lost connection to scan stream');
        try { source.close(); } catch (_) {}
        hideNetworkScanOverlay();
    };
}

// Copy to Clipboard
async function copyToClipboard(text) {
    try {
        await navigator.clipboard.writeText(text);
        showToast('success', 'Copied!', 'Text copied to clipboard');
    } catch (err) {
        showToast('error', 'Copy Failed', 'Could not copy to clipboard');
    }
}

// Format Date
function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
}

// Debounce
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}
