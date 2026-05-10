document.addEventListener('DOMContentLoaded', function () {
    // Mobiscroll setup
    mobiscroll.setOptions({
        theme: 'ios',
        themeVariant: 'dark'
    });

    var inst = mobiscroll.eventcalendar('#demo-desktop-month-view', {
    theme: 'ios',
    themeVariant: 'light',
    clickToCreate: false,
    dragToCreate: false,
    dragToMove: false,
    dragToResize: false,
    eventDelete: false,
    view: {
        calendar: { labels: true },
    },
    onEventClick: function (args) {
        mobiscroll.toast({
        message: args.event.title,
        });
    },
    });

    mobiscroll.getJson(
    'https://trial.mobiscroll.com/events/?vers=5',
    function (events) {
        inst.setEvents(events);
    },
    'jsonp',
    );
  

    const calendar = mobiscroll.eventcalendar('#calendar', {
        view: {
            calendar: { type: 'week' }
        },

        data: [],

        onEventClick: function (args) {
            console.log('Clicked:', args.event);
        },

        onEventUpdate: function (args) {
            fetch(`/calendar/events/${args.event.id}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    startTime: args.event.start.toISString(),
                    endTime: args.event.end.toISOString()
                })
            });
        },

        onCellClick: function (args) {
            const title = prompt("Event title:");
            if (!title) return;

            const start = args.date;
            const end = new Date(new Date(start).getTime() + 60 * 60 * 1000);

            fetch('/calendar/events', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    title: title,
                    startTime: start.toISOString(),
                    endTime: end.toISOString()
                })
            }).then(() => refreshEvents());
        }
    });

    let selectedDate = null;

    calendar.settings.onCellClick = function (args) {
        selectedDate = args.date;
        document.getElementById('eventModal').classList.remove('hidden');
    }

    document.getElementById('saveEvent').addEventListener('click', () => {
        const title = document.getElementById('eventTitle').value;

        if (!title) return;

        const start = selectedDate;
        const end = new Date(start.getTime() + 60*60*1000);

        fetch('/calendar/events', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                title,
                startTime: start.toISOString(),
                endTime: end.toISOString()
            })
        }).then(() => {
            refreshEvents();
            document.getElementById('eventModal').classList.add('hidden');
        });
    });

    // 🔥 Load events from backend
    async function loadEvents() {
        const res = await fetch('/calendar/events');
        const data = await res.json();

        return data.map(e => ({
            id: e.eventID,
            title: e.title,
            start: e.startTime,
            end: e.endTime,
            color: e.color,
            cssClass: 'custom-event'
        }));
    }

    async function refreshEvents() {
        document.body.style.opacity = 0.7;

        const events = await loadEvents();
        calendar.setEvents(events);

        document.body.style.opacity = 1;
    }

    refreshEvents();

    // Generate schedule button
    document.getElementById('generateBtn').addEventListener('click', () => {
        fetch('/calendar/generate', { method: 'POST' })
            .then(() => refreshEvents());
    });

    // Sync button (you’ll implement backend later)
    document.getElementById('syncBtn').addEventListener('click', async () => {
        await fetch('/calendar/sync/google', { method: 'POST' });
        refreshEvents();
    });

});