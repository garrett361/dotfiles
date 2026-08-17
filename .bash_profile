# bash reads only the first of ~/.bash_profile, ~/.bash_login, ~/.profile that exists, and
# RHEL-family skel ships a .bash_profile while Debian-family does not. Without this file, .profile
# never runs on those hosts and neither does anything it sets: PATH, the toolchain env, the ssh agent.
[ -f "$HOME/.profile" ] && . "$HOME/.profile"
