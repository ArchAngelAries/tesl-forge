# Boards

Two ways: a **new board** (a picture on one of the five original board bases) or **edits** to a board (every prop,
texture, light, effect and animation, plus things you add).

## New board (Boards page)
- Name, wide image (it's cut to the table), base board (Original, Isle of Madness, Alliance War, Elsweyr, Realms of
  Oblivion), mode *rotation* (added to the random board choice) or *replace* (replaces the base), texture size 2048/4096.
- Command line: `tesl board new --mod my-mod --name "Greenwood Table" --image table.png --base Original --mode rotation`

## Edit a board
1. Click **Edit board**. The board picture shows every object; click one to select it, or pick from the list.
2. Hide, move, rotate, resize, tint, add glow, or retexture props; change lights and overall lighting; change effects and
   animations. **Reset** undoes an object.
3. **Add** things by clicking on the picture where they go:
   - models: OBJ, GLB/glTF, zip; FBX, .blend, DAE, 3DS, STL, PLY, USD through Blender (if installed);
   - flat images (cut-outs), lights, particle effects (embers, mist, fireflies, sparks, snow, magic, smoke, bubbles);
   - motion: spin, bob, sway, pulse, float.
- Command line: `tesl board map --base Original`, then `tesl board edit ...`, `tesl board add model|image|light|effect ...`,
  `tesl board move`, `tesl board take` (see AGENTS.md).

## Tips
- When two mods replace the same base board, the later one in the load order wins.
- Boards are visual: they also load online (only you see them).
- Glass-like (alpha-blended) models render opaque for now.
- Players can force a board for testing from TESL: Everlasting's F10 menu.
