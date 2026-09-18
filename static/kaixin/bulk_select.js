(function () {
    function uniqueValues(checkedBoxes) {
        const seen = {};
        const values = [];
        checkedBoxes.forEach(function (box) {
            if (!seen[box.value]) {
                seen[box.value] = true;
                values.push(box.value);
            }
        });
        return values;
    }

    function initBulkForm(form) {
        const selectAllId = form.getAttribute('data-select-all');
        const countId = form.getAttribute('data-count');
        const selectAll = selectAllId ? document.getElementById(selectAllId) : null;
        const countLabel = countId ? document.getElementById(countId) : null;
        const buttons = form.querySelectorAll('[data-bulk-action]');

        function boxes() {
            return Array.prototype.slice.call(
                document.querySelectorAll('input.ip-select[name="ips"][form="' + form.id + '"]')
            );
        }

        function selectedBoxes() {
            return boxes().filter(function (box) { return box.checked; });
        }

        function selectedCount() {
            return uniqueValues(selectedBoxes()).length;
        }

        function setIpChecked(ip, checked) {
            boxes().forEach(function (box) {
                if (box.value === ip) {
                    box.checked = checked;
                }
            });
        }

        function sync() {
            const all = boxes();
            const checked = selectedBoxes();
            const count = uniqueValues(checked).length;
            if (selectAll) {
                selectAll.checked = all.length > 0 && checked.length === all.length;
                selectAll.indeterminate = checked.length > 0 && checked.length < all.length;
            }
            if (countLabel) {
                countLabel.textContent = count + ' selected';
            }
            buttons.forEach(function (button) {
                button.disabled = count === 0;
            });
        }

        if (selectAll) {
            selectAll.addEventListener('change', function () {
                boxes().forEach(function (box) {
                    box.checked = selectAll.checked;
                });
                sync();
            });
        }

        boxes().forEach(function (box) {
            box.addEventListener('change', function () {
                setIpChecked(box.value, box.checked);
                sync();
            });
        });

        form.addEventListener('submit', function (event) {
            const count = selectedCount();
            if (count === 0) {
                event.preventDefault();
                return;
            }
            const submitter = event.submitter;
            const template = submitter && submitter.getAttribute('data-confirm');
            if (template) {
                const message = template.replace(/\{n\}/g, String(count));
                if (!window.confirm(message)) {
                    event.preventDefault();
                }
            }
        });

        sync();
    }

    document.querySelectorAll('form[data-bulk-select]').forEach(initBulkForm);
})();
