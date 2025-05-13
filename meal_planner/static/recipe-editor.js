// Function to trigger HTMX diff update
function triggerDiffUpdate(elementContainingForm) {
    console.log('[recipe-editor.js] triggerDiffUpdate called for element:', elementContainingForm);
    const form = elementContainingForm.closest('form');
    if (form) {
        const diffWrapper = document.getElementById('diff-content-wrapper');
        const formData = htmx.values(form);
        console.log('[recipe-editor.js] Form data for diff update:', formData);
        if (diffWrapper) {
            htmx.ajax('POST', '/recipes/ui/update-diff', {
                target: diffWrapper,
                swap: 'innerHTML',
                values: formData, // Send all form values
                source: elementContainingForm // Element that triggered the update
            });
        } else {
            console.error('Diff wrapper #diff-content-wrapper not found.');
        }
    } else {
        console.error('Could not find parent form to trigger diff update.');
    }
}

// UIkit Sortable event handling
function initializeUikitSortables() {
    // Ensure UIkit is available
    if (typeof UIkit === 'undefined') {
        // console.warn('UIkit not available for sortable initialization.');
        return;
    }

    const lists = [
        document.getElementById('ingredients-list'),
        document.getElementById('instructions-list')
    ];

    lists.forEach(listElement => {
        if (listElement && listElement.hasAttribute('uk-sortable')) {
            // Re-apply/refresh UIkit sortable to ensure it picks up new children
            UIkit.sortable(listElement, {handle: '.drag-handle'}); 

            if (!listElement._uikitSortableStopListenerAttached) {
                UIkit.util.on(listElement, 'stop', function (event) {
                    console.log('[recipe-editor.js] UIkit sortable \'stop\' event fired for target:', event.target);
                    triggerDiffUpdate(event.target);
                });
                listElement._uikitSortableStopListenerAttached = true;
            }
        }
    });
}

// Initialize sortables on initial page load
document.addEventListener('DOMContentLoaded', function() {
    initializeUikitSortables();
    setTimeout(() => {
        if (typeof UIkit !== 'undefined') {
            const ingredientsList = document.getElementById('ingredients-list');
            const instructionsList = document.getElementById('instructions-list');
            if (
                (ingredientsList && !ingredientsList._uikitSortableStopListenerAttached) ||
                (instructionsList && !instructionsList._uikitSortableStopListenerAttached)
            ) {
                initializeUikitSortables();
            }
        }
    }, 500);
});

// Re-initialize sortables after HTMX content swaps
document.body.addEventListener('htmx:afterSettle', function(event) {
    initializeUikitSortables();
}); 
