# ALRS v2 Frontend

Flutter application for the Automated Literature Review System.

## Structure

```
frontend/
├── pubspec.yaml           # Flutter dependencies
├── lib/
│   ├── main.dart          # App entry point
│   ├── app.dart           # Material app + routing
│   ├── models/            # Data models (mirrors backend Pydantic)
│   ├── services/          # API client services
│   ├── providers/         # State management
│   ├── screens/           # Full-page screens
│   │   ├── home/
│   │   ├── search/
│   │   ├── results/
│   │   ├── chat/
│   │   └── settings/
│   └── widgets/           # Reusable components
│       ├── paper_card.dart
│       ├── citation_graph.dart
│       ├── progress_bar.dart
│       └── ...
├── test/                  # Widget + unit tests
└── web/                   # Flutter web assets
```

## Target Platforms

- Web (primary)
- Desktop (Windows, macOS, Linux)
- Mobile (iOS, Android) — stretch goal
