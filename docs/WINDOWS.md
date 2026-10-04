# DAWSync on Windows

The Mac producer publishes a folder containing `session.rpp`, `manifest.json`,
`audio`, `DAWSync.lua`, and `codec.lua`. Keep the complete folder together.

For a quick playback test, wait for the complete folder to download and open
`session.rpp`. Nothing else needs to be installed. The helper setup below is only
needed to publish recording, arrangement, edit, and mix changes back to Ableton.

## First session

1. In Google Drive for desktop, make the band's exchange folder available offline.
2. Wait for the complete revision to download, then open `session.rpp` in REAPER 7.
3. Open Actions → Show action list → New action → Load ReaScript.
4. Select `DAWSync.lua` beside the project. Keep `codec.lua` beside that script.
5. Run the action. It verifies the files and opens a **local working copy** in
   REAPER's resource folder. Work in that copy, rather than the published folder.
6. Add the action to a toolbar or assign a shortcut if desired.

## Working

Record, edit, rearrange, and mix normally. Save the working project. With the
helper running, it waits eight seconds and for playback/recording to stop, then
renders the top-level tracks and a master reference. Effects and automation are
printed on this machine, so the producer needs none of your Windows plugins.

The master reference is muted in the exchanged project. The working copy keeps
your native effects and edits; exchanged versions are rendered audio. Group
children are represented by their parent bus so the mix does not double up.

Start the DAWSync action again after restarting REAPER. Its watcher lives inside
REAPER while the application is running. A failed/cancelled render publishes no
valid manifest and preserves your working project; save again to retry.

Your recording directory is `recordings` relative to the working project. New
recordings are included in the next renders automatically.

## Incoming revisions

The running helper checks for an incoming Ableton update every twenty seconds.
Once all files verify and playback stops, it opens a new local working copy.
Unsaved edits or a pending outgoing save postpone reception. The previous working
copy remains on disk with its native edits. Competing incoming branches require
opening the chosen published `session.rpp` and starting DAWSync explicitly.
The Mac app preserves divergent revisions rather than merging simultaneous
musical changes automatically.

## Current limits

- Ableton Live 12 Standard and REAPER 7 are the target versions.
- Constant tempo and constant time signatures such as 3/4, 5/4, 6/8, and 7/8
  are supported. Tempo or time-signature changes stop transfer explicitly.
- Audio cuts/stretching/FX/automation are printed into full-length tracks.
- Bus and master FX parameters are retained in native projects, not translated.
- Mono/stereo RIFF WAV up to 192 kHz is supported; RF64 and multichannel audio
  require a later adapter.
- Four seconds of tail is the default. Set a longer tail on the Mac for long
  reverbs/delays. The helper currently adds four seconds on the return trip.

The source song is never overwritten by the Mac app. Packages use short ASCII
filenames, and project audio paths are relative. Creative names live in the track
labels and manifest. Checksums detect missing, partially synced, or modified files.
