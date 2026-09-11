document.addEventListener('DOMContentLoaded', () => {
    if (window.lucide) window.lucide.createIcons();
    document.querySelectorAll('input[type="file"][accept^="image/"]').forEach(input => {
        let objectURL;
        let preview;
        input.addEventListener('change', () => {
            if (objectURL) URL.revokeObjectURL(objectURL);
            if (preview) preview.remove();
            const file = input.files[0];
            if (!file || !['image/jpeg', 'image/png', 'image/webp'].includes(file.type) || file.size > 5 * 1024 * 1024) return;
            objectURL = URL.createObjectURL(file);
            preview = document.createElement('img');
            preview.src = objectURL;
            preview.alt = 'پیش‌نمایش تصویر انتخاب‌شده';
            preview.className = 'image-preview';
            input.after(preview);
        });
    });
    const status = document.querySelector('[data-maintenance-poll]');
    if (status) {
        let stopped = false;
        const poll = async () => {
            if (stopped) return;
            try {
                const response = await fetch(status.dataset.maintenancePoll, {credentials: 'same-origin', cache: 'no-store'});
                if (response.redirected || response.status === 403) { stopped = true; return; }
                if (!response.ok) throw new Error('request failed');
                const data = await response.json();
                if (!data.active) { location.reload(); return; }
                status.textContent = data.summary || 'عملیات در حال اجراست…';
            } catch (_) { status.textContent = 'ارتباط موقتاً قطع شده؛ برای دریافت نتیجه دوباره تلاش می‌کنیم…'; }
            setTimeout(poll, 5000);
        };
        setTimeout(poll, 5000);
    }
});
