"""
MkDocs macros module for SCIRM documentation.
Provides safe defaults for build information and git metadata.
"""

import os
import subprocess
from datetime import datetime


def define_env(env):
    """
    Define macros and variables for MkDocs.
    """
    
    @env.macro
    def get_build_date():
        """Get current build date in ISO format."""
        return datetime.now().strftime("%Y-%m-%d")
    
    @env.macro
    def get_git_commit():
        """Get current git commit hash (short)."""
        try:
            result = subprocess.run(
                ['git', 'rev-parse', '--short', 'HEAD'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return "unknown"
    
    @env.macro
    def get_git_branch():
        """Get current git branch name."""
        try:
            result = subprocess.run(
                ['git', 'branch', '--show-current'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return "main"
    
    # Set up macros_info dictionary with safe defaults
    env.variables['macros_info'] = {
        'build_date': get_build_date(),
        'git_short_commit': get_git_commit(),
        'git_branch': get_git_branch(),
        'version': os.environ.get('SCIRM_VERSION', '1.0.0'),
        'environment': os.environ.get('SCIRM_ENV', 'development')
    }
    
    # Additional utility macros
    @env.macro
    def scirm_version():
        """Get SCIRM version."""
        return env.variables['macros_info']['version']
    
    @env.macro
    def build_info():
        """Get formatted build information."""
        info = env.variables['macros_info']
        return f"Built on {info['build_date']} from commit {info['git_short_commit']}"
