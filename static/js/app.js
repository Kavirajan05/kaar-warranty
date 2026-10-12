// Northfield University SAP Warranty Management - Minimal Vanilla JS

document.addEventListener('DOMContentLoaded', function () {
    // 1. Live Instant Table Search for Exceptions & Reports
    const searchInput = document.getElementById('tableSearchInput');
    if (searchInput) {
        searchInput.addEventListener('keyup', function () {
            const query = this.value.toLowerCase().trim();
            const tableRows = document.querySelectorAll('.filterable-table tbody tr');
            tableRows.forEach(row => {
                const text = row.innerText.toLowerCase();
                if (text.includes(query)) {
                    row.style.display = '';
                } else {
                    row.style.display = 'none';
                }
            });
        });
    }

    // 2. Client-side Quick Filter synchronization
    const filterForm = document.getElementById('exceptionFilterForm');
    if (filterForm) {
        const selects = filterForm.querySelectorAll('select');
        selects.forEach(select => {
            select.addEventListener('change', function () {
                filterForm.submit();
            });
        });
    }

    // 3. Resolve Confirmation Modal / Dialog
    const resolveForms = document.querySelectorAll('.form-resolve-claim');
    resolveForms.forEach(form => {
        form.addEventListener('submit', function (e) {
            const confirmed = window.confirm("Are you sure you want to mark this warranty claim as RESOLVED? This will update the SAP exception status and generate an immutable audit log entry.");
            if (!confirmed) {
                e.preventDefault();
            }
        });
    });

    // 4. Auto-dismiss flash alerts after 5 seconds
    const alerts = document.querySelectorAll('.alert-dismissible');
    alerts.forEach(alert => {
        setTimeout(() => {
            const bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
            if (bsAlert) {
                bsAlert.close();
            }
        }, 5000);
    });
});
