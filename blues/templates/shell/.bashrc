## Pre-flight checks
# Test for an interactive shell.
if [[ $- != *i* ]] ; then
    # Shell is non-interactive.  Be done now!
    return
fi

# append to the history file, don't overwrite it
shopt -s histappend
# reformat multiline commands
shopt -s cmdhist
# check the window size after each command
shopt -s checkwinsize
# If set, the pattern "**" used in a pathname expansion context will
# match all files and zero or more directories and subdirectories.
shopt -s globstar

## Internal variables
# Prompt colors
COLOR_BLACK="\[\e[30;49m\]"
COLOR_RED="\[\e[31;49m\]"
COLOR_GREEN="\[\e[32;49m\]"
COLOR_YELLOW="\[\e[33;49m\]"
COLOR_BLUE="\[\e[34;49m\]"
COLOR_MAGENTA="\[\e[35;49m\]"
COLOR_CYAN="\[\e[36;49m\]"
COLOR_WHITE="\[\e[37;49m\]"
COLOR_NONE="\[\e[0m\]"

## Environment
export HISTCONTROL=ignoreboth
export HISTIGNORE='ls:ll:l:bg:fg:history'
export HISTTIMEFORMAT='%F %T '

export HISTSIZE=10000
export HISTFILESIZE=10000

export PATH="/sbin:/usr/sbin:/usr/local/bin:$PATH"
[[ -d "$HOME/bin" ]] && export PATH="$HOME/bin:$PATH"

## User Features
[[ -f ~/.bash_aliases ]] && . ~/.bash_aliases

if [[ "$TERM" != "dumb" ]] && which dircolors >/dev/null ; then
    [[ -r ~/.dircolors ]] && eval "$(dircolors -b ~/.dircolors)" || eval "$(dircolors -b)"
fi

## Shell features
[[ -f /etc/bash_completion ]] && . /etc/bash_completion

## GUI features
[[ $TERM == 'xterm' ]] && TITLEBAR="\[\e]2;\u@\h:\w\a\]" || TITLEBAR=""

## logic
function prompt_cmd_venv {
    [[ -n "${VIRTUAL_ENV}" ]] \
    && echo "${COLOR_NONE}:${COLOR_WHITE}${VIRTUAL_ENV##*/}${COLOR_NONE}"
}

function prompt_cmd {
    # Cursor color is determined by the exit status of the last command.
    [[ "$?" -eq 0 ]] \
    && CLR_CURSOR="${COLOR_GREEN}" \
    || CLR_CURSOR="${COLOR_RED}"

    # Host color is set by the provisioning system
    CLR_HOST="{{ host_color }}"

    # User color is determined by the current UID, root=red
    [[ "${EUID}" -eq 0 ]] \
    && CLR_USER="${COLOR_RED}" \
    || CLR_USER="${COLOR_GREEN}"

    STATUS_VENV="$(prompt_cmd_venv)"

    PS1="${TITLEBAR}\
${CLR_USER}\u${COLOR_NONE}@${CLR_HOST}\h${COLOR_NONE}\
${STATUS_VENV}:${COLOR_CYAN}\w\
${CLR_CURSOR}\\$ ${COLOR_NONE}"

}

PROMPT_COMMAND=prompt_cmd
