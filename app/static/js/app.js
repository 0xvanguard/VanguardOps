const API_BASE = '/api/v1';

async function fetchJSON(url) {
    try {
        const response = await fetch(`${API_BASE}${url}`);
        if (!response.ok) throw new Error('Network response was not ok');
        return await response.json();
    } catch (error) {
        console.error('Error fetching data:', error);
        return [];
    }
}

function getPriorityBadge(priority) {
    if (!priority) return '';
    const p = priority.toLowerCase();
    const className = `badge-${p}`;
    return `<span class="badge ${className}">${priority}</span>`;
}

function getStatusBadge(status) {
    if (!status) return '';
    const s = status.toLowerCase().replace('_', '');
    const className = `badge-${s}`;
    return `<span class="badge ${className}">${status}</span>`;
}

function formatTime(isoString) {
    const d = new Date(isoString);
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

async function updateDashboard() {
    // 1. Fetch data from the API
    const tickets = await fetchJSON('/tickets/');
    const workflows = await fetchJSON('/workflows/');
    const logs = await fetchJSON('/activity-log/');
    
    // 2. Compute Statistics
    const openTickets = tickets.filter(t => t.status !== 'CLOSED' && t.status !== 'RESOLVED');
    const criticalTickets = tickets.filter(t => t.priority === 'CRITICAL' && t.status !== 'CLOSED');
    const runningWfs = workflows.filter(w => w.status === 'RUNNING' || w.status === 'PENDING');
    
    document.getElementById('stat-tickets').textContent = openTickets.length;
    document.getElementById('stat-critical').textContent = criticalTickets.length;
    document.getElementById('stat-workflows').textContent = runningWfs.length;
    document.getElementById('stat-events').textContent = logs.length;
    
    // 3. Render Tickets Table
    const tbody = document.querySelector('#tickets-table tbody');
    tbody.innerHTML = '';
    
    if (tickets.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" style="text-align:center; color: var(--text-secondary)">No tickets found</td></tr>';
    } else {
        // Sort newest first
        tickets.sort((a,b) => b.id - a.id).slice(0, 7).forEach(t => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>#${t.id}</td>
                <td style="font-weight:500">${t.title}</td>
                <td>${getPriorityBadge(t.priority)}</td>
                <td>${getStatusBadge(t.status)}</td>
                <td style="color:var(--text-secondary); font-size:0.85rem">${t.assigned_to || 'Unassigned'}</td>
            `;
            tbody.appendChild(tr);
        });
    }
    
    // 4. Render Activity Timeline
    const timeline = document.getElementById('activity-timeline');
    timeline.innerHTML = '';
    
    if (logs.length === 0) {
        timeline.innerHTML = '<div style="color: var(--text-secondary); text-align:center; margin-top:20px;">No activity recorded yet</div>';
    } else {
        logs.slice(0, 15).forEach(log => {
            const item = document.createElement('div');
            item.className = 'timeline-item';
            
            let dotClass = '';
            if (log.event_type.includes('succeed') || log.event_type.includes('created')) dotClass = 'success';
            if (log.event_type.includes('fail') || log.event_type.includes('error')) dotClass = 'warning';
            
            const detailsStr = log.details_json ? JSON.stringify(log.details_json, null, 2) : '';
            const detailsHtml = detailsStr !== '{}' && detailsStr !== '' ? `<div class="timeline-desc">${detailsStr}</div>` : '';
            
            item.innerHTML = `
                <div class="timeline-dot ${dotClass}"></div>
                <div class="timeline-content">
                    <div class="timeline-time">${formatTime(log.timestamp_utc)} • ${log.entity_type.toUpperCase()} #${log.entity_id}</div>
                    <div class="timeline-title">${log.event_type.replace('_', ' ').toUpperCase()}</div>
                    ${detailsHtml}
                </div>
            `;
            timeline.appendChild(item);
        });
    }
}

// Initialization and automatic polling
document.addEventListener('DOMContentLoaded', () => {
    updateDashboard();
    setInterval(updateDashboard, 5000); // Auto-refresh every 5s for dynamic feel
});

// Expose refresh function to global scope for the button
window.fetchData = updateDashboard;
