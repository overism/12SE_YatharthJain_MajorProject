if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/static/sw.js')
    .then(function(registration) {
      console.log('Service Worker registered with scope:', registration.scope);
    })
    .catch(function(error) {
      console.error('Service Worker registration failed:', error);
    });
}

function showPopup(title, message, onClose = null) {
    const popup = document.createElement("div");
    popup.className = "popup";

    popup.innerHTML = `
        <div class="popup-box">
            <h2>${title}</h2>
            <p>${message}</p>
            <button id="popup-close">OK</button>
        </div>
    `;

    document.body.appendChild(popup);

    document.getElementById("popup-close").onclick = () => {
        popup.remove();
        if (typeof onClose === "function") {
            onClose();
        }
    };
}

const loginForm = document.getElementById('loginForm');
if (loginForm) {
    loginForm.addEventListener('submit', function(event) {
        event.preventDefault();

        fetch('/login_validation', {
            method: 'POST',
            body: new FormData(this)
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                showPopup("Login Successful", data.message, () => {
                    window.location.href = "/home";
                });
            } else {
                showPopup("Login Failed", data.message);
            }
        })
        .catch(() => {
            showPopup("Error", "Unable to login. Please try again.");
        });
    });
}

const signupForm = document.getElementById('signupForm');
if (signupForm) {
    signupForm.addEventListener('submit', function(e) {
        e.preventDefault();

        if (!this.checkValidity()) {
            this.reportValidity();
            return;
        }

        const pw = document.getElementById('password').value;
        const cpw = document.getElementById('confirmPassword').value;

        if (pw !== cpw) {
            showPopup("Signup Error", "Passwords do not match.");
            return;
        }

        fetch("/add_user", {
            method: "POST",
            body: new FormData(this)
        })
        .then(res => res.json())
        .then(data => {
            showPopup(data.title, data.message, () => {
                if (data.success) {
                    window.location.href = "/login";
                }
            });
        })
        .catch(() => {
            showPopup("Server Error", "Something went wrong. Please try again later.");
        });
    });
}

document.querySelectorAll('.game-card').forEach(card => {
  card.addEventListener('click', () => {
    const banner = card.dataset.banner;
    const link = card.dataset.link;
    const overlay = document.getElementById('overlay');

    overlay.style.backgroundImage = `url(${banner})`;
    overlay.classList.add('active');

    setTimeout(() => {
      window.location.href = link;
    }, 600);
  });
});

const saveBioBtn = document.getElementById('saveBio');
if (saveBioBtn) {
  saveBioBtn.addEventListener('click', (e) => {
    e.preventDefault();
    saveBio();
  });
}

async function saveBio() {
  const bio = document.getElementById('bioEditor').value;
  const bioStatus = document.getElementById('bioStatus');
  bioStatus.textContent = 'Saving...';

  try {
    const response = await fetch('/save-bio', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ bio: bio })
    });

    if (response.ok) {
      bioStatus.textContent = 'Saved';
      setTimeout(() => bioStatus.textContent = '', 2000);
    } else {
      bioStatus.textContent = 'Error saving bio';
    }
  } catch (error) {
    bioStatus.textContent = 'Error saving bio';
  }
}

const resetBioBtn = document.getElementById('resetBio');
if (resetBioBtn) {
  resetBioBtn.addEventListener('click', (e) => {
    e.preventDefault();
    const bioEditor = document.getElementById('bioEditor');
    const bioStatus = document.getElementById('bioStatus');
    if (bioEditor) bioEditor.value = '{{ user.userBio }}';
    if (bioStatus) {
      bioStatus.textContent = 'Reset';
      setTimeout(() => bioStatus.textContent = '', 1400);
    }
  });
}

// Handle Avatar Upload
const avatarForm = document.getElementById('avatarForm');
if (avatarForm) {
  avatarForm.addEventListener('submit', (e) => {
    e.preventDefault();

    const formData = new FormData(e.target);
    fetch('/upload-avatar', {
      method: 'POST',
      body: formData
    })
    .then(response => response.json())
    .then(data => {
      if (data.status === 'success') {
        const avatar = document.getElementById('profileAvatar');
        if (avatar) avatar.src = data.filepath;
      }
    });
  });
}

const searchForm = document.getElementById('searchForm');
const searchSlot = document.querySelector('.search-slot');
const menuSearch = document.querySelector('.menu-search');

function moveSearch() {
  if (window.innerWidth <= 640) {
    if (!menuSearch.contains(searchForm)) {
      menuSearch.appendChild(searchForm);
    }
  } else {
    if (!searchSlot.contains(searchForm)) {
      searchSlot.appendChild(searchForm);
    }
  }
}

window.addEventListener('resize', moveSearch);
window.addEventListener('load', moveSearch);