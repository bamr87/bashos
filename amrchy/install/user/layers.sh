# Run each layer's per-user setup: install/layers/<name>/user.sh, as the user,
# after the rest of the user setup. See docs/layers.md.
for layer_dir in "$OMARCHY_INSTALL"/layers/*/; do
  layer_dir=${layer_dir%/}
  [[ -f $layer_dir/user.sh ]] || continue
  echo "Layer ${layer_dir##*/}: user setup"
  LAYER_DIR=$layer_dir LAYER_NAME=${layer_dir##*/} bash -eE -c 'source "$LAYER_DIR/user.sh"'
done
