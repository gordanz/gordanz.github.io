#!/usr/bin/env bash

set -Eeuo pipefail

readonly PREVIEW_RUBY_VERSION="${PREVIEW_RUBY_VERSION:-3.4.10}"
readonly PREVIEW_PORT="${PREVIEW_PORT:-4000}"
readonly SITE_DIRECTORY="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This setup script currently supports macOS only." >&2
  exit 1
fi

if ! command -v brew >/dev/null 2>&1; then
  echo "Homebrew is required. Install it from https://brew.sh and run this script again." >&2
  exit 1
fi

if ! command -v rbenv >/dev/null 2>&1; then
  echo "Installing the Ruby version manager..."
  brew install rbenv ruby-build
fi

export RBENV_ROOT="${RBENV_ROOT:-$HOME/.rbenv}"
export PATH="$(brew --prefix rbenv)/bin:$RBENV_ROOT/bin:$RBENV_ROOT/shims:$PATH"

if ! rbenv versions --bare | grep -Fxq "$PREVIEW_RUBY_VERSION"; then
  echo "Installing Ruby $PREVIEW_RUBY_VERSION..."
  rbenv install "$PREVIEW_RUBY_VERSION"
fi

cd "$SITE_DIRECTORY"
rbenv local "$PREVIEW_RUBY_VERSION"
export RBENV_VERSION="$PREVIEW_RUBY_VERSION"

install_gem_if_missing() {
  local gem_name="$1"

  if ! rbenv exec gem list --installed --exact "$gem_name" >/dev/null 2>&1; then
    echo "Installing $gem_name..."
    rbenv exec gem install "$gem_name" --no-document
  fi
}

install_gem_if_missing github-pages
install_gem_if_missing webrick

echo
echo "Starting the local preview with Ruby $(rbenv exec ruby --version)..."
echo "Open http://localhost:$PREVIEW_PORT in your browser."
echo "Press Ctrl+C to stop the preview."
echo

exec rbenv exec jekyll serve \
  --livereload \
  --host 127.0.0.1 \
  --port "$PREVIEW_PORT"
