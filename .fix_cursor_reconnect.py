from pathlib import Path
p=Path('app.py')
s=p.read_text(encoding='utf-8')
old='''            if "stream not found" in message and hasattr(self.connection, "_reconnect"):\n                self.connection._reconnect()\n                try:\n                    if parameters is None:\n                        self.raw.execute(sql)\n                    else:\n                        self.raw.execute(sql, parameters)\n                    return self\n'''
new='''            if "stream not found" in message and hasattr(self.connection, "_reconnect"):\n                self.connection._reconnect()\n                # Recreate the cursor after reconnecting. The previous cursor\n                # remains attached to the expired HRANA stream, so retrying it\n                # directly would fail with the same 404 again.\n                self.raw = self.connection.raw.cursor()\n                try:\n                    if parameters is None:\n                        self.raw.execute(sql)\n                    else:\n                        self.raw.execute(sql, parameters)\n                    return self\n'''
assert old in s, 'expected Turso reconnect block not found'
s=s.replace(old,new,1)
p.write_text(s,encoding='utf-8')
