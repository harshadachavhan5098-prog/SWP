document.querySelector('form.auth-card')?.addEventListener('submit', (event) => {
  const password = event.currentTarget.querySelector('input[name="password"]');
  if (password && password.autocomplete === 'new-password' && !/(?=.*[a-z])(?=.*[A-Z])(?=.*\d).{12,}/.test(password.value)) {
    event.preventDefault(); password.setCustomValidity('Use at least 12 characters with uppercase, lowercase, and a number.'); password.reportValidity(); password.setCustomValidity('');
  }
});
