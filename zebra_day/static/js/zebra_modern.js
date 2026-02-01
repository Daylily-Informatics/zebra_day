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
    
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `
        <div class="toast-icon">
            <i class="fas ${icons[type] || icons.info}"></i>
        </div>
        <div class="toast-content">
            <div class="toast-title">${title}</div>
            <div class="toast-message">${message}</div>
        </div>
        <button class="toast-close" onclick="this.parentElement.remove()">&times;</button>
    `;
    
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
        const p = overlay.querySelector('p');
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

