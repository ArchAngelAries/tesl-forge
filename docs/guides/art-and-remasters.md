# Art and remasters

Replace original images with your own at any resolution. The game shows them at the original size, so higher resolutions
simply look sharper. Turning the mod off restores the originals.

## What can be replaced
- Card art (by card name), avatars and portraits, deck banners, arena and profile images, and other images the game loads
  by path. The **Asset browser** labels every asset and says whether and how a mod can change it ("changeable").
- Not yet: premium (animated) card versions, sprites packed into shared atlases, UI images built into prefabs.

## In the app (Remaster art page)
1. **Replace a card's art:** search the card, drop your image, choose *crop to the original's shape* or *stretch*.
2. **Replace any other image:** find it in the Asset browser, copy its path, drop your image.
3. Remasters made so far are listed at the top with **Restore original**.

## Command line
```
tesl assets export --kind texture --contains golden_saint --out <a folder>   export originals first to keep framing
tesl replace image --mod my-remaster --card "Fiery Imp" --image imp-4k.png
tesl replace image --mod my-remaster --asset <asset path> --image new.png [--fit crop|stretch]
tesl replace list --mod my-remaster
tesl replace remove --mod my-remaster --asset <asset path>
```

## Tips
- Export the original first and keep its framing; the game crops the same areas.
- Remasters are **local visual mods**: they also load in online launches (only you see them).
- AI-upscaled originals are still Bethesda's art: fine for your own use, check their terms before sharing or selling.
