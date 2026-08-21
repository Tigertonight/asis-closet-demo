#!/usr/bin/env bash

# Temporary migration bridge for environments that still export the old prefix.
promote_legacy_selfit_env() {
  local legacy_key selfit_key legacy_value
  while IFS='=' read -r legacy_key legacy_value; do
    case "$legacy_key" in
      ORI_*) selfit_key="SELFIT_${legacy_key#ORI_}" ;;
      STYLIST_ORI_*) selfit_key="STYLIST_SELFIT_${legacy_key#STYLIST_ORI_}" ;;
      OPENCLAW_ORI_*) selfit_key="OPENCLAW_SELFIT_${legacy_key#OPENCLAW_ORI_}" ;;
      *) continue ;;
    esac
    if [ -z "${!selfit_key+x}" ]; then
      export "$selfit_key=$legacy_value"
    fi
  done < <(env)
}
