document.body.addEventListener('click', function(event) {
    var deleteButton = event.target.closest('.delete-item-button');
    if (deleteButton) {
        console.log('Delete button clicked:', deleteButton);
        event.preventDefault(); // Stop default button action

        var rowToRemove = deleteButton.closest('div');
        var form = document.getElementById('edit-review-form');

        if (!rowToRemove || !form) {
            console.error('Could not find row to remove or the form.');
            return;
        }

        console.log('Initiating DELETE request for row:', rowToRemove);
        htmx.ajax('DELETE', '/recipes/ui/remove-item', {
            target: rowToRemove,
            swap: 'outerHTML'
        }).then(function(response) {
            console.log('DELETE request successful. Initiating POST for diff update...');
            htmx.ajax('POST', '/recipes/ui/update-diff', {
                source: form,
                target: '#diff-content-wrapper',
                swap: 'innerHTML'
            });
            console.log('Update diff POST request triggered.');
        }).catch(function(error) {
            console.error('Error during DELETE or subsequent POST:', error);
        });
    }
});
