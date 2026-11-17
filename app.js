const form = document.getElementById('form');
const file = document.getElementById('file');
const label = document.getElementById('file-label');
const submit = document.getElementById('submit');
const message = document.getElementById('message');
const working = document.getElementById('working');
const results = document.getElementById('results');
const step = document.getElementById('step');
file.addEventListener('change', () => { label.textContent = file.files[0]?.name || 'Choisir un fichier DS2 ou DSS'; });
const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));
form.addEventListener('submit', async (event) => {
  event.preventDefault();
  if (!file.files.length) return;
  submit.disabled = true; message.textContent = ''; working.hidden = false; results.hidden = true;
  step.textContent = 'Envoi du fichier…';
  try {
    const body = new FormData(); body.append('file', file.files[0]);
    const response = await fetch('/api/jobs', { method: 'POST', body });
    const data = await response.json();
    if (!response.ok) throw Error(data.error || 'Envoi impossible.');
    const jobId = data.id;
    for (;;) {
      await sleep(2500);
      const statusRes = await fetch(`/api/jobs/${jobId}`);
      if (!statusRes.ok) throw Error('Le serveur a redémarré ou le traitement a expiré.');
      const job = await statusRes.json(); step.textContent = job.step;
      if (job.status === 'error') throw Error(job.step);
      if (job.status === 'done') {
        document.getElementById('text').value = job.text;
        for (const kind of ['wav', 'txt', 'srt']) {
          document.getElementById(kind).href = `/api/jobs/${jobId}/download/${kind}`;
        }
        results.hidden = false; working.hidden = true; break;
      }
    }
  } catch (error) { working.hidden = true; message.textContent = error.message; }
  finally { submit.disabled = false; }
});
