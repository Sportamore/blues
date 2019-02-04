# ~/.bash_profile

# This file is sourced by bash for login shells.  The following line
# runs your .bashrc and is recommended by the bash info pages.
[[ -f ~/.bashrc ]] && . ~/.bashrc
{% if dotenv -%}
# Managed by app.configure_environment from shell_env
[[ -f ~/.env ]] && . ~/.env
{% for key in env.iterkeys() %}
export {{ key }}
{%- endfor %}

[[ -d "$PYTHON_VENV" ]] && . "$PYTHON_VENV/bin/activate"
{%- endif -%}
