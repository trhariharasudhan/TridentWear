// About / Contact / FAQ / Policies / 404 / Offline
import { mountChrome, $, icon, toast, busy, esc } from '../ui.js';
import { api } from '../api.js';
import { CONFIG } from '../config.js';

const page = document.body.dataset.page;
await mountChrome({ page: page === 'about' ? 'about' : '' });

if (page === 'contact') {
  const b = CONFIG.brand;
  $('[data-contact-cards]').innerHTML = [
    [icon.mail, 'Email', `<a href="mailto:${b.email}">${esc(b.email)}</a>`],
    [icon.phone, 'Phone', `<a href="tel:${b.phone.replace(/\s/g, '')}">${esc(b.phone)}</a>`],
    [icon.whatsapp, 'WhatsApp', `<a href="https://wa.me/${b.whatsapp}" target="_blank" rel="noopener">Chat with us</a>`],
    [icon.pin, 'Studio', esc(b.address)],
  ].map(([i, t, v]) => `<div class="contact-card">${i}<div><b>${t}</b><div class="muted">${v}</div></div></div>`).join('');

  const form = $('[data-contact-form]');
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const err = $('[data-error]');
    if (!form.checkValidity()) { err.textContent = 'Please fill in your name, a valid email and a message (10+ characters).'; return; }
    err.textContent = '';
    const btn = $('button', form);
    busy(btn, true, 'Sending');
    try {
      const res = await api.contact(Object.fromEntries(new FormData(form)));
      form.reset();
      toast(res?.message || 'Message sent — we will reply soon.');
    } catch (ex) { err.textContent = ex.message; }
    finally { busy(btn, false); }
  });
}
