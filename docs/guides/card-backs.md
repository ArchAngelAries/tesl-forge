# Card backs

Any number per mod. The image is cropped into the game's card shape (portrait, about 4:7).

- **Price 0** = free for everyone with the mod. A price sells it for gold in the offline store (*Special Offers*).
- **Unlock text** explains how to get it.
- Size 1024 or 2048.
- Players choose it in **Collection > card backs**.

```
tesl cardback new --mod my-mod --name "Dragon Seal" --image seal.png --price 300 [--unlock "..."] [--size 2048]
tesl cardback list --mod my-mod
tesl cardback remove --mod my-mod --name "Dragon Seal"
```
