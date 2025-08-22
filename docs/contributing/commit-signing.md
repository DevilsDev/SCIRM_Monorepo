# Commit Signing Setup - SSH Keys (Windows-Friendly)

## Overview

All commits to SCIRM must be cryptographically signed to ensure authenticity and maintain audit trails. We use SSH commit signing as it's more Windows-friendly than GPG.

## SSH Signing Setup

### 1. Generate SSH Key

```bash
# Generate new SSH key (if you don't have one)
ssh-keygen -t ed25519 -C "your.email@company.com"

# When prompted, save to default location:
# Windows: C:\Users\YourName\.ssh\id_ed25519
# Press Enter for no passphrase (or set one for extra security)
```

### 2. Add SSH Key to SSH Agent

```bash
# Start SSH agent (Windows)
eval "$(ssh-agent -s)"

# Add your SSH private key
ssh-add ~/.ssh/id_ed25519
```

### 3. Add SSH Key to GitHub

1. Copy your **public** key:
   ```bash
   cat ~/.ssh/id_ed25519.pub
   ```

2. Go to GitHub → Settings → SSH and GPG keys
3. Click "New SSH key"
4. **Important**: Set "Key type" to **"Signing Key"** (not Authentication)
5. Paste your public key
6. Add a descriptive title like "SCIRM Development - Signing"

### 4. Configure Git for SSH Signing

```bash
# Set your identity (use your GitHub email)
git config --global user.name "Your Full Name"
git config --global user.email "your.github.email@company.com"

# Configure SSH signing
git config --global gpg.format ssh
git config --global user.signingkey ~/.ssh/id_ed25519.pub
git config --global commit.gpgsign true

# Optional: Sign tags by default too
git config --global tag.gpgsign true
```

### 5. Verify Setup

```bash
# Make a test commit
git commit --allow-empty -m "test: verify SSH signing setup"

# Check if commit is signed
git log --show-signature -1
```

**Expected output**:
```
commit abc123... (signed)
Good "git" signature for your.email@company.com with ED25519 key SHA256:...
```

## Windows-Specific Instructions

### Using Git Bash (Recommended)
```bash
# In Git Bash, SSH agent should work automatically
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_ed25519
```

### Using PowerShell
```powershell
# Start SSH agent service
Get-Service ssh-agent | Set-Service -StartupType Automatic -PassThru | Start-Service

# Add key
ssh-add $env:USERPROFILE\.ssh\id_ed25519
```

### Using WSL (Windows Subsystem for Linux)
```bash
# In WSL, keys are typically at:
ssh-keygen -t ed25519 -C "your.email@company.com"
# Save to: /home/username/.ssh/id_ed25519

# Configure git in WSL
git config --global user.signingkey /home/username/.ssh/id_ed25519.pub
```

## Troubleshooting

### "gpg failed to sign the data"
```bash
# Check SSH agent is running
ssh-add -l

# If no identities, add your key
ssh-add ~/.ssh/id_ed25519

# Verify git config
git config --global --list | grep -E "(user\.|gpg\.|commit\.)"
```

### "Bad signature" or verification fails
1. Ensure you added the key as a **Signing Key** in GitHub (not Authentication)
2. Verify the email matches your GitHub account
3. Check the public key path is correct:
   ```bash
   git config --global user.signingkey
   cat ~/.ssh/id_ed25519.pub
   ```

### SSH agent not persisting (Windows)
```bash
# Add to your ~/.bashrc or ~/.bash_profile
if [ -z "$SSH_AUTH_SOCK" ]; then
   eval "$(ssh-agent -s)"
   ssh-add ~/.ssh/id_ed25519
fi
```

### Different SSH key for different repos
```bash
# For SCIRM repository specifically
cd /path/to/SCIRM_Monorepo
git config user.signingkey ~/.ssh/id_ed25519_scirm.pub
git config user.email "your.scirm.email@company.com"
```

## Verification Checklist

Before committing to SCIRM:

- [ ] SSH key generated and added to SSH agent
- [ ] Public key added to GitHub as **Signing Key**
- [ ] Git configured with correct email and signing key
- [ ] `commit.gpgsign` set to `true`
- [ ] Test commit shows "signed" status
- [ ] GitHub shows "Verified" badge on commits

## Multiple Key Management

### Work vs Personal Keys
```bash
# Work key for SCIRM
git config user.email "work@company.com"
git config user.signingkey ~/.ssh/id_ed25519_work.pub

# Personal key for other projects
git config --global user.email "personal@gmail.com"
git config --global user.signingkey ~/.ssh/id_ed25519_personal.pub
```

### SSH Config for Multiple Keys
Create `~/.ssh/config`:
```
# Work GitHub
Host github-work
    HostName github.com
    User git
    IdentityFile ~/.ssh/id_ed25519_work

# Personal GitHub  
Host github-personal
    HostName github.com
    User git
    IdentityFile ~/.ssh/id_ed25519_personal
```

## Security Best Practices

### Key Security
- **Never share private keys** (`id_ed25519` without `.pub`)
- Use passphrases for additional security
- Rotate keys annually
- Remove old keys from GitHub when no longer used

### Repository Security
- Always verify "Verified" badge appears on GitHub
- Report unsigned commits to security team
- Use `git log --show-signature` to audit commit signatures

## Emergency Procedures

### Lost SSH Key
1. Generate new key pair
2. Add new public key to GitHub as Signing Key
3. Update git config with new key path
4. Remove old key from GitHub
5. Notify security team of key rotation

### Compromised Key
1. **Immediately** remove key from GitHub
2. Generate new key pair
3. Update all repositories with new key
4. Report incident to security team
5. Review recent commits for unauthorized changes

## IDE Integration

### VS Code
Install "Git Graph" extension to visualize signed commits:
- Signed commits show 🔒 icon
- Unsigned commits show ⚠️ warning

### IntelliJ/PyCharm
Enable commit signing in VCS settings:
- File → Settings → Version Control → Git
- Check "Sign off commits" 
- Verify signing key path

## Support

For SSH signing issues:
- Check GitHub's SSH signing documentation
- Test with `ssh -T git@github.com`
- Verify SSH agent with `ssh-add -l`
- Contact IT support for Windows-specific SSH agent issues

---

**Remember**: Signed commits are required for all SCIRM contributions. This ensures code authenticity and maintains our security compliance.
