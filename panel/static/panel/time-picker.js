(() => {
    'use strict';

    function initializeClocks() {
        const fields = document.querySelectorAll('[data-clock-field]');
        if (!fields.length || typeof HTMLDialogElement === 'undefined') return;

        const dialog = document.createElement('dialog');
        dialog.className = 'clock-dialog';
        dialog.id = 'panel-time-picker';
        dialog.dir = 'rtl';
        dialog.setAttribute('aria-labelledby', 'clock-title');
        dialog.setAttribute('aria-describedby', 'clock-hint');
        dialog.innerHTML = `
            <h2 id="clock-title">انتخاب ساعت</h2>
            <p id="clock-hint" class="clock-hint">ساعت و دقیقه را انتخاب کنید. ساعت‌ها به صورت ۲۴ساعته هستند.</p>
            <output class="clock-preview" dir="ltr" aria-live="polite"></output>
            <div class="clock-columns">
                <div><span id="clock-hour-label" class="clock-column-label">ساعت</span>
                    <div class="clock-wheel" data-part="hour" role="listbox" aria-labelledby="clock-hour-label"></div></div>
                <div><span id="clock-minute-label" class="clock-column-label">دقیقه</span>
                    <div class="clock-wheel" data-part="minute" role="listbox" aria-labelledby="clock-minute-label"></div></div>
            </div>
            <div class="clock-actions">
                <button type="button" class="clock-apply">تأیید ساعت</button>
                <button type="button" class="clock-cancel">انصراف</button>
                <button type="button" class="clock-clear">پاک کردن ساعت</button>
            </div>`;
        document.body.append(dialog);

        const pad = value => String(value).padStart(2, '0');
        const persian = value => String(value).replace(/\d/g, digit => '۰۱۲۳۴۵۶۷۸۹'[Number(digit)]);
        const normalize = value => value.replace(/[۰-۹٠-٩]/g, digit => {
            const code = digit.charCodeAt(0);
            return String(code >= 0x06f0 ? code - 0x06f0 : code - 0x0660);
        }).replace(/[\u200e\u200f\u061c\u202a-\u202c\u2066-\u2069]/g, '').trim();
        const selected = {hour: 9, minute: 0};
        let activeInput = null;
        let activeButton = null;

        function centerOption(option) {
            const wheel = option.parentElement;
            const top = option.getBoundingClientRect().top - wheel.getBoundingClientRect().top;
            wheel.scrollTop += top - (wheel.clientHeight - option.offsetHeight) / 2;
        }

        function renderSelection() {
            dialog.querySelector('.clock-preview').textContent = persian(`${pad(selected.hour)}:${pad(selected.minute)}`);
            dialog.querySelectorAll('.clock-wheel').forEach(wheel => {
                wheel.querySelectorAll('button').forEach(option => {
                    const isSelected = Number(option.dataset.value) === selected[wheel.dataset.part];
                    option.setAttribute('aria-selected', String(isSelected));
                    option.tabIndex = isSelected ? 0 : -1;
                });
            });
        }

        dialog.querySelectorAll('.clock-wheel').forEach(wheel => {
            const count = wheel.dataset.part === 'hour' ? 24 : 60;
            for (let value = 0; value < count; value += 1) {
                const option = document.createElement('button');
                option.type = 'button';
                option.className = 'clock-option';
                option.setAttribute('role', 'option');
                option.dataset.value = value;
                option.textContent = persian(pad(value));
                option.addEventListener('click', () => {
                    selected[wheel.dataset.part] = value;
                    renderSelection();
                    centerOption(option);
                });
                option.addEventListener('keydown', event => {
                    let next = value;
                    if (event.key === 'ArrowDown') next = (value + 1) % count;
                    else if (event.key === 'ArrowUp') next = (value + count - 1) % count;
                    else if (event.key === 'Home') next = 0;
                    else if (event.key === 'End') next = count - 1;
                    else return;
                    event.preventDefault();
                    selected[wheel.dataset.part] = next;
                    renderSelection();
                    const nextOption = wheel.children[next];
                    nextOption.focus({preventScroll: true});
                    centerOption(nextOption);
                });
                wheel.append(option);
            }
        });

        fields.forEach(field => {
            const input = field.querySelector('input');
            const button = field.querySelector('[data-clock-open]');
            const label = input.labels?.[0]?.textContent.trim() || 'ساعت';
            button.hidden = false;
            button.setAttribute('aria-label', `انتخاب ${label}`);
            button.setAttribute('aria-controls', dialog.id);
            button.addEventListener('click', () => {
                activeInput = input;
                activeButton = button;
                const value = normalize(input.value);
                const match = /^(\d{1,2}):(\d{2})(?::\d{2})?$/.exec(value);
                selected.hour = match && Number(match[1]) < 24 ? Number(match[1]) : 9;
                selected.minute = match && Number(match[2]) < 60 ? Number(match[2]) : 0;
                dialog.querySelector('#clock-title').textContent = `انتخاب ${label}`;
                dialog.querySelector('.clock-clear').hidden = input.required;
                renderSelection();
                dialog.showModal();
                dialog.querySelectorAll('[aria-selected="true"]').forEach(centerOption);
                dialog.querySelector('[aria-selected="true"]').focus({preventScroll: true});
            });
        });

        const fullDay = document.getElementById('id_is_full_day');
        if (fullDay) {
            const syncFullDay = () => fields.forEach(field => {
                field.querySelector('input').disabled = fullDay.checked;
                field.querySelector('[data-clock-open]').disabled = fullDay.checked;
            });
            fullDay.addEventListener('change', syncFullDay);
            syncFullDay();
        }

        function applyValue(value) {
            activeInput.value = value;
            activeInput.dispatchEvent(new Event('input', {bubbles: true}));
            activeInput.dispatchEvent(new Event('change', {bubbles: true}));
            dialog.close();
        }

        dialog.querySelector('.clock-apply').addEventListener('click', () => applyValue(`${pad(selected.hour)}:${pad(selected.minute)}`));
        dialog.querySelector('.clock-clear').addEventListener('click', () => applyValue(''));
        dialog.querySelector('.clock-cancel').addEventListener('click', () => dialog.close());
        dialog.addEventListener('close', () => activeButton?.focus());
        dialog.addEventListener('click', event => {
            if (event.target !== dialog) return;
            const rect = dialog.getBoundingClientRect();
            if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) dialog.close();
        });
    }

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initializeClocks);
    else initializeClocks();
})();
