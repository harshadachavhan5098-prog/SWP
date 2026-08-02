document.querySelectorAll('.post-media').forEach((image) => image.addEventListener('error', () => image.closest('.post-card')?.classList.add('media-unavailable')));
