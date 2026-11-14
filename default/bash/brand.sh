brand_file() {
  local here=""

  here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
  if [[ -f $here/../brand.toml ]]; then
    printf '%s\n' "$here/../brand.toml"
    return 0
  fi
  if [[ -n ${BRAND_PATH:-} && -f $BRAND_PATH/default/brand.toml ]]; then
    printf '%s\n' "$BRAND_PATH/default/brand.toml"
    return 0
  fi
  return 1
}

brand_load() {
  local file="" section="" line="" key="" value=""

  file=$(brand_file) || return 1
  section=""
  BRAND_ID=""
  BRAND_NAME=""
  BRAND_ENV=""

  while IFS= read -r line || [[ -n $line ]]; do
    [[ $line =~ ^[[:space:]]*# ]] && continue
    [[ $line =~ ^[[:space:]]*$ ]] && continue
    if [[ $line =~ ^\[([A-Za-z0-9_-]+)\][[:space:]]*$ ]]; then
      section="${BASH_REMATCH[1]}"
      continue
    fi
    [[ $section == "identity" ]] || continue
    if [[ $line =~ ^[[:space:]]*([A-Za-z0-9_]+)[[:space:]]*=[[:space:]]*\"([^\"]*)\"[[:space:]]*$ ]]; then
      key="${BASH_REMATCH[1]}"
      value="${BASH_REMATCH[2]}"
      case "$key" in
      id) BRAND_ID="$value" ;;
      name) BRAND_NAME="$value" ;;
      env) BRAND_ENV="$value" ;;
      esac
    fi
  done <"$file"

  [[ -n $BRAND_ID && -n $BRAND_NAME && -n $BRAND_ENV ]] || return 1
  BRAND_COMMAND="$BRAND_ID"
  BRAND_CONFIG_DIR="$BRAND_ID"
  BRAND_SHARE_DIR="$BRAND_ID"
  BRAND_PATH_VAR="${BRAND_ENV}_PATH"
  export BRAND_ID BRAND_NAME BRAND_ENV BRAND_COMMAND BRAND_CONFIG_DIR BRAND_SHARE_DIR BRAND_PATH_VAR
}
