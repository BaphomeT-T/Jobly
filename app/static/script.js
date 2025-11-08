// Add interactivity to the landing page

document.addEventListener('DOMContentLoaded', function() {
    // Job card hover effects
    const jobCards = document.querySelectorAll('.job-card');
    
    jobCards.forEach(card => {
        card.addEventListener('mouseenter', function() {
            this.style.boxShadow = '0px 1px 2px 0px rgba(16, 24, 40, 0.08), 0px 1px 3px 0px rgba(16, 24, 40, 0.08)';
            this.style.borderColor = '#A2A6A4';
        });
        
        card.addEventListener('mouseleave', function() {
            if (!this.classList.contains('job-card-hover')) {
                this.style.boxShadow = 'none';
                this.style.borderColor = '#CFD4D1';
            }
        });
    });
    
    // Bookmark button functionality
    const bookmarkButtons = document.querySelectorAll('.bookmark-btn');
    
    bookmarkButtons.forEach(btn => {
        btn.addEventListener('click', function(e) {
            e.stopPropagation();
            const svg = this.querySelector('svg path');
            const isFilled = svg.getAttribute('fill') !== 'none';
            
            if (isFilled) {
                svg.setAttribute('fill', 'none');
                svg.setAttribute('stroke', '#141514');
            } else {
                svg.setAttribute('fill', '#141514');
                svg.setAttribute('stroke', 'none');
            }
        });
    });
    
    // Login button functionality
    const loginBtn = document.querySelector('.btn-login');
    if (loginBtn) {
        loginBtn.addEventListener('click', function() {
            window.location.href = '/login';
        });
    }
    
    // Register buttons functionality
    const registerEmployerBtn = document.querySelector('.btn-register-employer');
    if (registerEmployerBtn) {
        registerEmployerBtn.addEventListener('click', function() {
            window.location.href = '/register/employer/step1';
        });
    }
    
    const registerCandidateBtn = document.querySelector('.btn-register-candidate');
    if (registerCandidateBtn) {
        registerCandidateBtn.addEventListener('click', function() {
            window.location.href = '/register/empleado/step1';
        });
    }
    
    // Icon buttons functionality
    const iconButtons = document.querySelectorAll('.icon-btn');
    iconButtons.forEach(btn => {
        btn.addEventListener('click', function() {
            const label = this.getAttribute('aria-label');
            console.log(`${label} clicked`);
        });
    });
    
    // Job card click functionality
    jobCards.forEach(card => {
        card.addEventListener('click', function() {
            // Add navigation to job detail page here
            console.log('Job card clicked');
        });
    });
    
    // Smooth scroll for anchor links
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function (e) {
            e.preventDefault();
            const target = document.querySelector(this.getAttribute('href'));
            if (target) {
                target.scrollIntoView({
                    behavior: 'smooth',
                    block: 'start'
                });
            }
        });
    });
});

