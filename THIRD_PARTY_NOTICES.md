# Third-party notices

`directing-multicam` is designed to work with the open-source
[`polysync`](https://github.com/jianshuo/polysync) package and takes architectural
inspiration from the `wjs-syncing-multicam` and `wjs-editing-multicam` skills in
[`jianshuo/claude-skills`](https://github.com/jianshuo/claude-skills).

Both upstream projects are distributed under the MIT License.

This repository does not vendor upstream source code in the initial
implementation; `polysync` is installed as a Python dependency and invoked
through its public CLI.
