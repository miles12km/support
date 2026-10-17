const toggle = document.getElementById('menuToggle');
const links = document.getElementById('navLinks');

toggle.addEventListener('click', () => {
  links.classList.toggle('open');
});

links.querySelectorAll('a').forEach((link) => {
  link.addEventListener('click', () => links.classList.remove('open'));
});

// Portal tabs
const tabButtons = document.querySelectorAll('.tab-btn');
const signupForm = document.getElementById('signupForm');
const loginForm = document.getElementById('loginForm');

function showTab(name) {
  tabButtons.forEach((btn) => btn.classList.toggle('active', btn.dataset.tab === name));
  signupForm.classList.toggle('active', name === 'signup');
  loginForm.classList.toggle('active', name === 'login');
}

tabButtons.forEach((btn) => {
  btn.addEventListener('click', () => showTab(btn.dataset.tab));
});

document.querySelectorAll('.switch-link').forEach((link) => {
  link.addEventListener('click', (e) => {
    e.preventDefault();
    showTab(link.dataset.switch);
  });
});

signupForm.addEventListener('submit', (e) => {
  e.preventDefault();
  if (signupForm.password.value !== signupForm.confirm.value) {
    alert('Passwords do not match.');
    return;
  }
  signupForm.reset();
  alert('Account initialized! Welcome to EZTech IT Services.');
  showTab('login');
});

loginForm.addEventListener('submit', (e) => {
  e.preventDefault();
  loginForm.reset();
  alert('Access granted. Logged in successfully.');
});
