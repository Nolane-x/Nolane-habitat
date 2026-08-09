# Alpha.0 Architecture

```text
Normal folder / ZIP / loose source file
                 |
                 v
          Source Bridge
                 |
      canonical source tree
                 |
          Workspace Compiler
        /        |        \
       v         v         v
  File index   Symbols   Relations
       \         |         /
        \        v        /
             SQLite Twin
                 |
       +---------+---------+
       |         |         |
       v         v         v
    orient    inspect    query
       |                   |
       +------ agent ------+
                 |
        +--------+--------+
        |                 |
        v                 v
  Transaction Engine  Execution Engine
        |                 |
        v                 v
 canonical source     typed receipts
        |
        v
 refresh semantic twin

HTML source -> Semantic HTML observer -> UI element objects
```

The semantic twin is rebuildable. It is never the source of truth.
