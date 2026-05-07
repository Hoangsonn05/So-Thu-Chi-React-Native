# AI Assistant Feature - Integration Documentation

## 📦 Architecture Overview

```
App.tsx (Root)
  ├── AIFloatingIsland (Collapsed State)
  │   ├── Draggable component
  │   ├── 50px x 50px Dynamic Island style
  │   └── Opens modal on press
  │
  ├── AIChatModal (Expanded State)
  │   ├── Full chat interface
  │   ├── Message history
  │   ├── Voice/Text input
  │   └── Auto-submit transactions
  │
  └── AIAssistantService
      ├── Prompt generation (generateAIPrompt)
      ├── API calls (callGeminiAPI)
      ├── Response parsing
      └── State management
```

---

## 🔧 Component Structure

### 1. **AIFloatingIsland.tsx**
- **Purpose**: Collapsed, always-on-screen floating component
- **Size**: 50x50px (Dynamic Island style)
- **Features**:
  - Draggable with PanResponder
  - Tap to expand
  - Glassmorphic design (#7C4DFF)
  - Material icon: auto_awesome
  - Z-index: 999 (always on top)
  - Pointer events handled correctly

### 2. **AIChatModal.tsx**
- **Purpose**: Full-screen chat modal when expanded
- **Features**:
  - Smooth slide-up animation (300ms)
  - Message history display
  - Text input field
  - Voice button (mic icon)
  - Send button with loading state
  - Suggestion chips
  - Transaction data preview
  - Auto-scroll to latest message

### 3. **AIAssistantService.ts**
- **Purpose**: Core AI logic (extracted from Java)
- **Key Functions**:
  - `generateAIPrompt()` - Creates Gemini prompt
  - `processUserInput()` - Main entry point
  - `parseAIResponse()` - Parses JSON response
  - `getConversationHistory()` - Message tracking

### 4. **gemini-client.ts**
- **Purpose**: HTTP client for Gemini API
- **Model**: `gemini-1.5-flash`
- **API Key**: `AIzaSyBk2tRqMVasNvZP13P9O5eymUiD-rSc31A`
- **Response Parsing**:
  - Extracts text from `candidates[0].content.parts[0].text`
  - Cleans JSON markdown (```json```)
  - Parses nested JSON substrings

---

## 🎯 Response JSON Schema

```json
{
  "so_tien": 45000,
  "ghi_chu": "Ăn phở sáng",
  "danh_muc": "Ăn uống",
  "ngay": "17/04/2024",
  "auto_submit": true,
  "thong_bao": "Đã ghi nhận chi 45,000 VND cho Ăn uống",
  "action_type": "CHI"
}
```

---

## 🔌 Integration Points

### In App.tsx:
```typescript
// 1. Import components
import AIFloatingIsland from './src/components/AIFloatingIsland';
import AIChatModal from './src/components/AIChatModal';

// 2. State management
const [isAIChatModalVisible, setIsAIChatModalVisible] = useState(false);
const [currentDate, setCurrentDate] = useState(/* today */);

// 3. Render in JSX
<AIFloatingIsland
  isExpanded={isAIChatModalVisible}
  onPress={() => setIsAIChatModalVisible(true)}
/>

<AIChatModal
  isVisible={isAIChatModalVisible}
  onClose={() => setIsAIChatModalVisible(false)}
  currentDate={currentDate}
  onTransactionDetected={(data) => {
    // Save transaction to database
  }}
/>
```

### In Transaction Repository:
```typescript
// When onTransactionDetected fires:
async function saveAIDetectedTransaction(data) {
  const transaction = {
    amount: data.amount,
    note: data.note,
    category: data.category,
    date: parseDate(data.date),
    type: data.type, // 0: Expense, 1: Income
  };
  
  await transactionRepository.add(transaction);
  await firestoreService.syncTransaction(transaction);
}
```

---

## ✅ Testing Checklist

### Phase 1: Component Tests
- [ ] AIFloatingIsland renders at bottom-right
- [ ] Dragging works smoothly
- [ ] Z-index correct (no overlap issues)
- [ ] Pointer events don't block underlying UI
- [ ] Tap expands to modal

### Phase 2: Modal Tests
- [ ] Modal slides up smoothly
- [ ] Input field works (text entry)
- [ ] Send button enabled only when text present
- [ ] Messages display correctly
- [ ] Auto-scroll to latest message
- [ ] Close button dismisses modal

### Phase 3: API Tests
- [ ] API key valid
- [ ] Network request succeeds
- [ ] Response parsing works
- [ ] Error handling for bad responses
- [ ] Loading state shows during request

### Phase 4: Features Tests
- [ ] User input processed correctly
- [ ] AI response parsed (JSON)
- [ ] Transaction data extracted
- [ ] Auto-submit works
- [ ] Manual submit option available
- [ ] Message history tracked

### Phase 5: Integration Tests
- [ ] No side-effects on existing features
- [ ] Transactions saved to database
- [ ] Firestore sync works
- [ ] App performance unchanged
- [ ] No memory leaks
- [ ] Works offline gracefully

### Phase 6: UX Tests
- [ ] Voice input button functional*
- [ ] Suggestion chips work
- [ ] Animation smooth at 60fps
- [ ] No crashes on edge cases
- [ ] Keyboard handled properly
- [ ] Accessibility checks

*Voice input requires platform-specific setup (react-native-speech-recognizer or equivalent)

---

## 🚀 Voice Input Setup (TODO)

Voice transcription currently shows placeholder alert. To enable:

1. **Install dependency**:
   ```bash
   npm install react-native-speech-recognizer
   # or similar library
   ```

2. **Update AIChatModal.tsx**:
   ```typescript
   import { useSpeechRecognizer } from 'react-native-speech-recognizer';
   
   const handleVoicePress = async () => {
     setIsListening(true);
     try {
       const transcript = await startListening({ language: 'vi-VN' });
       setInput(transcript);
     } finally {
       setIsListening(false);
     }
   };
   ```

3. **Add Android permissions** (AndroidManifest.xml):
   ```xml
   <uses-permission android:name="android.permission.RECORD_AUDIO" />
   ```

---

## ⚠️ Important Notes

1. **Security**: API Key is exposed in client code. Consider:
   - Using a backend proxy
   - Environment variables in build process
   - API rate limiting

2. **Auto-Submit**: Only enabled when AI is very confident
   - Default: false (manual confirmation)
   - User can adjust threshold

3. **Conversation History**: Kept in memory only
   - Cleared on app restart
   - Consider persistence if needed

4. **No Side-Effects Guarantee**:
   - AI components render only when authenticated
   - AIFloatingIsland has `pointerEvents="box-only"`
   - Modal overlay prevents interaction with underlying UI
   - All existing features work unchanged

---

## 📝 File Manifest

```
src/
├── components/
│   ├── AIFloatingIsland.tsx         (NEW - UI component)
│   └── AIChatModal.tsx              (NEW - UI component)
├── services/
│   └── AIAssistantService.ts        (NEW - Logic service)
├── utils/
│   └── gemini-client.ts             (NEW - HTTP client)
├── config/
│   └── AIConfig.ts                  (NEW - Configuration)
├── hooks/
│   └── useAIAssistant.ts            (NEW - React hook)
└── App.tsx                          (MODIFIED - Integration)
```

---

## 🔍 Verification Steps

1. **Build Check**:
   ```bash
   npm run type-check
   # Should pass with no TypeScript errors
   ```

2. **Lint Check**:
   ```bash
   npm run lint
   # Should pass (or warnings only)
   ```

3. **Runtime Check**:
   - Start app
   - Log in
   - Purple floating island appears bottom-right
   - Tap to expand
   - Type test message
   - Click send
   - API responds
   - Check console for errors

4. **Feature Check**:
   - Verify no crashes
   - Verify existing features work
   - Check transaction auto-submit
   - Verify message history

---

## 🎓 Code References

**Original Java Implementation**:
- `source/HamchinhActivity.java` (lines 1402-1650+)
  - `showAiBottomSheet()` → `AIFloatingIsland + AIChatModal`
  - `callGeminiApi()` → `gemini-client.ts`
  - `getAiPrompt()` → `generateAIPrompt()`
  - Voice input handling → `AIChatModal voice button`

**Prompt Consistency**:
- Same Gemini model (gemini-1.5-flash)
- Same API endpoint
- Same API key
- Same response JSON structure
- Same category lists

---

## 📞 Troubleshooting

### Component won't render
- Ensure authenticated (`isAuthenticated` state is true)
- Check z-index (may be under other modals)

### API calls fail
- Verify API key is correct
- Check network connectivity
- Look for CORS issues (in browser)

### Messages not displaying
- Check JSON parsing logic
- Look at network response in DevTools
- Verify conversation history state

### Animations stuttering
- Check device performance
- Consider reducing animation duration
- Profile with React Native Debugger

### Memory leaks
- Check effect cleanup
- Verify no circular references
- Monitor heap in DevTools

---

## 📊 Metrics & Analytics (Optional)

Consider tracking:
- Frequency of AI usage
- Message count per session
- Auto-submit vs manual
- API response time
- Error rates
- User satisfaction

---

**Version**: 1.0
**Last Updated**: April 17, 2024
**Status**: Ready for testing
