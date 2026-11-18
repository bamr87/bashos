# Run each layer's system setup: a product built on this framework ships under
# install/layers/<name>/, and its system.sh runs here, as root in the installed
# target, after the rest of the system setup. See docs/layers.md.
for layer_dir in "$OMARCHY_INSTALL"/layers/*/; do
  layer_dir=${layer_dir%/}
  [[ -f $layer_dir/system.sh ]] || continue
  echo "Layer ${layer_dir##*/}: system setup"
  LAYER_DIR=$layer_dir LAYER_NAME=${layer_dir##*/} bash -eE -c 'source "$LAYER_DIR/system.sh"'
done
