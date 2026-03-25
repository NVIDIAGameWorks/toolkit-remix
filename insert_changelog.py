import pathlib

changelog = pathlib.Path("CHANGELOG.md")
lines = changelog.read_text().splitlines(keepends=True)
new_entry = "- Fixed selection panel showing no hierarchy or properties for certain imported USD assets by adding regex-based prototype resolution fallback\n"
lines.insert(80, new_entry)
changelog.write_text("".join(lines))
print("Done")
