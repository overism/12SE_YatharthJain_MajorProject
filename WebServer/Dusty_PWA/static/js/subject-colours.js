(function() {
    const DEFAULT_SUBJECT_COLOR_PALETTE = {
        orange: '#f5761c',
        blue: '#2563eb',
        green: '#15803d',
        red: '#dc2626',
        purple: '#7c3aed',
        yellow: '#d97706',
        amber: '#d97706',
        brown: '#92400e',
        teal: '#0891b2',
        pink: '#be185d',
    };

    window.SUBJECT_COLOR_PALETTE = window.SUBJECT_COLOR_PALETTE || DEFAULT_SUBJECT_COLOR_PALETTE;
    window.SUBJECT_COLOURS = window.SUBJECT_COLOURS || window.SUBJECT_COLOR_PALETTE;
    window.SUBJ_COLOURS = window.SUBJ_COLOURS || Object.values(window.SUBJECT_COLOURS);

    window.getSubjectColour = window.getSubjectColour || function(key) {
        const k = String(key || '').toLowerCase();
        const normalized = k === 'yellow' ? 'amber' : k;
        if (normalized && normalized in window.SUBJECT_COLOURS) return window.SUBJECT_COLOURS[normalized];
        return Object.values(window.SUBJECT_COLOURS)[0] || '#f5761c';
    };

    window.getSubjectColourName = window.getSubjectColourName || function(key) {
        return key || 'orange';
    };
})();
