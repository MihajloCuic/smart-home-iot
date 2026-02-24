const alarmState = document.getElementById('alarmState');
const timerRemaining = document.getElementById('timerRemaining');
const timerBlinking = document.getElementById('timerBlinking');
const timerIncrement = document.getElementById('timerIncrement');
const persons = document.getElementById('persons');
const display = document.getElementById('display');
const updated = document.getElementById('updated');

const alarmOffBtn = document.getElementById('alarmOff');
const timerSetBtn = document.getElementById('timerSetBtn');
const timerIncBtn = document.getElementById('timerIncBtn');
const timerStopBtn = document.getElementById('timerStopBtn');

const timerSetInput = document.getElementById('timerSetInput');
const timerIncInput = document.getElementById('timerIncInput');

function formatSeconds(seconds) {
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
}

async function fetchStatus() {
  const res = await fetch('/api/status');
  const data = await res.json();

  alarmState.textContent = data.alarm || '-';
  timerRemaining.textContent = formatSeconds(data.timer_remaining || 0);
  timerBlinking.textContent = data.timer_blinking ? 'Yes' : 'No';
  timerIncrement.textContent = `${data.timer_increment || 0}s`;
  persons.textContent = data.persons ?? 0;
  display.textContent = data.display || '-';
  if (data.updated) {
    updated.textContent = new Date(data.updated * 1000).toLocaleTimeString();
  }
}

alarmOffBtn.addEventListener('click', async () => {
  await fetch('/api/alarm/deactivate', { method: 'POST' });
});

timerSetBtn.addEventListener('click', async () => {
  const seconds = parseInt(timerSetInput.value || '0', 10);
  await fetch('/api/timer/set', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ seconds })
  });
});

timerIncBtn.addEventListener('click', async () => {
  const seconds = parseInt(timerIncInput.value || '1', 10);
  await fetch('/api/timer/increment', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ seconds })
  });
});

timerStopBtn.addEventListener('click', async () => {
  await fetch('/api/timer/stop', { method: 'POST' });
});

setInterval(fetchStatus, 1000);
fetchStatus();
