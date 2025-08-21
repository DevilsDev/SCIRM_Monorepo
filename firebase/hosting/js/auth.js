import { initializeApp } from 'https://www.gstatic.com/firebasejs/10.7.1/firebase-app.js';
import { getAuth, GoogleAuthProvider, signInWithRedirect, getRedirectResult, signOut } from 'https://www.gstatic.com/firebasejs/10.7.1/firebase-auth.js';

// Initialize Firebase with injected config
const app = initializeApp(window.firebaseConfig);
const auth = getAuth(app);
const provider = new GoogleAuthProvider();

// Configure Google provider
provider.addScope('email');
provider.addScope('profile');

/**
 * Handle Google Sign-In using redirect (avoids COOP issues)
 */
async function handleGoogleSignIn() {
    const loginBtn = document.getElementById('loginBtn');
    const errorDiv = document.getElementById('error');
    
    try {
        loginBtn.disabled = true;
        loginBtn.textContent = 'Redirecting to Google...';
        errorDiv.style.display = 'none';
        
        // Use redirect instead of popup to avoid COOP issues
        await signInWithRedirect(auth, provider);
        
    } catch (error) {
        console.error('Sign-in error:', error);
        
        let errorMessage = 'Sign-in failed. Please try again.';
        
        if (error.code === 'auth/network-request-failed') {
            errorMessage = 'Network error. Please check your connection.';
        }
        
        errorDiv.textContent = errorMessage;
        errorDiv.style.display = 'block';
        
        loginBtn.disabled = false;
        loginBtn.innerHTML = `
            <svg width="18" height="18" viewBox="0 0 24 24">
                <path fill="currentColor" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                <path fill="currentColor" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                <path fill="currentColor" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
                <path fill="currentColor" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
            </svg>
            Sign in with Google
        `;
    }
}

/**
 * Handle redirect result on page load
 */
async function handleRedirectResult() {
    try {
        const result = await getRedirectResult(auth);
        if (result) {
            const user = result.user;
            console.log('User signed in via redirect:', user.email);
            
            // Get ID token
            const idToken = await user.getIdToken();
            
            // Exchange ID token for session cookie
            const response = await fetch('/auth/callback', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ idToken }),
            });
            
            if (response.ok) {
                console.log('Session created successfully');
                // Redirect to documentation
                window.location.href = '/';
            } else {
                throw new Error(`Session creation failed: ${response.status}`);
            }
        }
    } catch (error) {
        console.error('Redirect result error:', error);
        const errorDiv = document.getElementById('error');
        if (errorDiv) {
            errorDiv.textContent = 'Authentication failed. Please try again.';
            errorDiv.style.display = 'block';
        }
    }
}

/**
 * Handle sign out
 */
async function handleSignOut() {
    try {
        await signOut(auth);
        // Clear session cookie by making request to logout endpoint
        await fetch('/auth/logout', { method: 'POST' });
        window.location.href = '/login';
    } catch (error) {
        console.error('Sign-out error:', error);
    }
}

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    // Handle redirect result first
    handleRedirectResult();
    
    const loginBtn = document.getElementById('loginBtn');
    if (loginBtn) {
        loginBtn.addEventListener('click', handleGoogleSignIn);
    }
    
    // Add sign-out functionality if on documentation pages
    const signOutBtn = document.getElementById('signOutBtn');
    if (signOutBtn) {
        signOutBtn.addEventListener('click', handleSignOut);
    }
});

// Export functions for global access
window.handleGoogleSignIn = handleGoogleSignIn;
window.handleSignOut = handleSignOut;
