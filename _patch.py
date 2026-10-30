p = "vector_drift/scenes/game.py"
s = open(p, encoding="utf-8").read()
start = s.index("            # Sync progress to cloud when authenticated.")
end = s.index("            self.audio.play(\"win\")", start)
print(start, end)
