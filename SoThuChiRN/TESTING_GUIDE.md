# AI Feature - Testing & Validation Guide

## 📋 Pre-Testing Checklist

### Code Quality
```bash
# 1. Type checking
npm run type-check
# Expected: No TypeScript errors

# 2. Linting (optional)
npm run lint
# Expected: No critical errors, warnings acceptable

# 3. Build test
npm run build
# Expected: Successful build, no fatal errors
```

### File Verification
- ✓ All 8 files exist in correct locations
- ✓ No duplicate file names
- ✓ All imports resolve correctly
- ✓ API key present in gemini-client.ts
- ✓ Colors defined in AIConfig.ts

---

## 🧪 Phase 1: Component Rendering Tests

### Test 1.1: App Launch & Auth
**Setup**: Deploy app, log in with valid credentials

**Steps**:
1. Launch app
2. Log in successfully
3. Navigate to any main transaction screen

**Expected Results**:
- ✓ App launches without crash
- ✓ No console errors
- ✓ Purple floating bubble appears at bottom-right
- ✓ Floating island is 50x50px
- ✓ Icon is visible (auto_awesome)
- ✓ Positioned consistently

**Actual Results**: 
```
[ ] Pass  [ ] Fail  [ ] Partial
Notes: _________________________________
```

### Test 1.2: Floating Island Appearance
**Setup**: App running, logged in

**Steps**:
1. Look at screen bottom-right
2. Verify visual appearance
3. Check z-index (should be above other UI)
4. Verify no UI obstruction

**Expected Results**:
- ✓ Floating island visible
- ✓ Icon shows clearly
- ✓ No overlap with other buttons
- ✓ Purple color (#7C4DFF) correct
- ✓ Shadow/elevation visible
- ✓ "Glassmorphic" effect subtle

**Actual Results**:
```
[ ] Pass  [ ] Fail  [ ] Partial
Notes: _________________________________
```

---

## 🧪 Phase 2: Interaction Tests

### Test 2.1: Dragging
**Setup**: App running, floating island visible

**Steps**:
1. Long press on floating island
2. Drag to new position (up, down, left, right)
3. Release
4. Tap on different location
5. Observe component behavior

**Expected Results**:
- ✓ Component tracks finger smoothly
- ✓ Drag indicator shows (status dot changes)
- ✓ After release, snaps back to position
- ✓ No lag or jumpy movement
- ✓ Pointer events not blocked elsewhere

**Actual Results**:
```
[ ] Pass  [ ] Fail  [ ] Partial
Notes: _________________________________
```

### Test 2.2: Tap to Expand
**Setup**: App running, floating island visible

**Steps**:
1. Tap floating island once (quick tap)
2. Observe modal animation
3. Wait for full expansion
4. Verify modal is interactable

**Expected Results**:
- ✓ Modal slides up smoothly (300ms)
- ✓ Overlay appears (50% black transparency)
- ✓ Modal fully visible and centered
- ✓ Header shows "Trợ Lý AI"
- ✓ Input field focused (optional)
- ✓ Floating island hidden during modal

**Actual Results**:
```
[ ] Pass  [ ] Fail  [ ] Partial
Notes: _________________________________
```

### Test 2.3: Close Modal
**Setup**: Modal fully expanded

**Steps**:
1. Click close button (X) in top-right
2. Or tap overlay outside modal
3. Observe collapse animation
4. Verify floating island reappears

**Expected Results**:
- ✓ Modal slides down smoothly (250ms)
- ✓ Floating island reappears immediately
- ✓ No residual UI artifacts
- ✓ App state unchanged
- ✓ No console errors

**Actual Results**:
```
[ ] Pass  [ ] Fail  [ ] Partial
Notes: _________________________________
```

---

## 🧪 Phase 3: Input & Message Tests

### Test 3.1: Text Input
**Setup**: Modal fully expanded, input field visible

**Steps**:
1. Tap input field
2. Type: `"Ăn phở sáng 45k"`
3. Observe text appears
4. Press backspace, verify deletion
5. Try emoji: `"☕ Cà phê 35k"`

**Expected Results**:
- ✓ Text appears as typed
- ✓ Cursor visible
- ✓ Backspace deletes correctly
- ✓ Emoji supported
- ✓ Max 500 chars enforced
- ✓ Send button enabled when text present

**Actual Results**:
```
[ ] Pass  [ ] Fail  [ ] Partial
Notes: _________________________________
```

### Test 3.2: Send Button
**Setup**: Modal open, text entered

**Steps**:
1. Type test message
2. Click send button
3. Observe loading state
4. Wait for response (2-3 seconds)
5. Check message history

**Expected Results**:
- ✓ Send button disabled during processing
- ✓ Loading spinner appears
- ✓ Status shows "✨ Chờ tớ chút nha ✨"
- ✓ After response: input clears
- ✓ Message appears in history (user bubble)
- ✓ AI response appears (assistant bubble)

**Actual Results**:
```
[ ] Pass  [ ] Fail  [ ] Partial
Notes: _________________________________
```

### Test 3.3: Message History
**Setup**: Modal with conversation history

**Steps**:
1. Send 3-4 messages in sequence
2. Scroll up to see older messages
3. Verify formatting and order
4. Check auto-scroll to latest

**Expected Results**:
- ✓ User messages appear right-aligned (purple)
- ✓ Assistant messages appear left-aligned (white)
- ✓ Timestamps correct (or not shown)
- ✓ Auto-scroll to bottom after each message
- ✓ Chat history scrollable

**Actual Results**:
```
[ ] Pass  [ ] Fail  [ ] Partial
Notes: _________________________________
```

### Test 3.4: Suggestion Chips
**Setup**: Modal just opened, no messages

**Steps**:
1. Observe suggestion chips at bottom
2. Tap chip: `"🍜 Phở sáng 45k"`
3. Verify text appears in input
4. Send message
5. Try another chip

**Expected Results**:
- ✓ Chips display with emoji and text
- ✓ Tap fills input field
- ✓ Emoji stripped, text only remains
- ✓ Can proceed to send
- ✓ Chips disappear after first message

**Actual Results**:
```
[ ] Pass  [ ] Fail  [ ] Partial
Notes: _________________________________
```

---

## 🧪 Phase 4: API & Response Tests

### Test 4.1: Gemini API Call
**Setup**: Modal open, internet connected

**Steps**:
1. Send message: `"Ăn phở sáng 45k"`
2. Monitor network (DevTools/Proxy)
3. Observe response
4. Check parsing

**Expected Results**:
- ✓ HTTP POST to `generativelanguage.googleapis.com`
- ✓ Response 200 OK
- ✓ JSON response contains candidates
- ✓ Text extracted successfully
- ✓ No network errors in console

**Network Request**:
```
URL: https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite-latest:generateContent?key=AIzaSy...
Method: POST
Body: { contents: [ { parts: [ { text: "..." } ] } ] }
Response: 200 OK
```

**Actual Results**:
```
[ ] Pass  [ ] Fail  [ ] Partial
Notes: _________________________________
```

### Test 4.2: Response Parsing
**Setup**: Multiple test messages sent

**Test Cases**:
1. Simple expense: `"Phở 45k"`
   - Expected: so_tien: 45000, action_type: "CHI"

2. Income: `"Lương tháng 10 triệu"`
   - Expected: so_tien: 10000000, action_type: "THU"

3. Complex: `"Thanh toán điện nước 800k vô tư`
   - Expected: so_tien: 800000, danh_muc related

**Expected Results**:
- ✓ JSON parsed successfully
- ✓ All fields present: so_tien, ghi_chu, danh_muc, ngay, auto_submit, thong_bao, action_type
- ✓ Amount in Vietnamese numerals converted correctly
- ✓ Date format: dd/MM/yyyy
- ✓ auto_submit: true (high confidence) or false (uncertain)

**Test Results**:
```
Case 1: [ ] Pass  [ ] Fail
Case 2: [ ] Pass  [ ] Fail
Case 3: [ ] Pass  [ ] Fail

Notes: _________________________________
```

### Test 4.3: Error Handling
**Setup**: Various error conditions

**Test Cases**:
1. Disconnect internet, send message
   - Expected: Network error shown

2. Send empty message
   - Expected: "Vui lòng nhập nội dung!" toast

3. API timeout (manual via DevTools throttling)
   - Expected: Graceful error message

4. Invalid JSON response (simulate)
   - Expected: Error message, no crash

**Actual Results**:
```
Case 1: [ ] Pass  [ ] Fail
Case 2: [ ] Pass  [ ] Fail
Case 3: [ ] Pass  [ ] Fail
Case 4: [ ] Pass  [ ] Fail

Notes: _________________________________
```

---

## 🧪 Phase 5: Transaction Integration Tests

### Test 5.1: Auto-Submit (auto_submit: true)
**Setup**: AI returns high-confidence response

**Steps**:
1. Send: `"Ăn phở 45k"`
2. AI responds with auto_submit: true
3. Observe message with transaction preview
4. Check if transaction auto-saved in DB

**Expected Results**:
- ✓ Response shows transaction data preview
- ✓ Shows: amount (💰), category (📁), note (📝)
- ✓ Transaction saved to database
- ✓ Toast: "✅ Đã Lưu"
- ✓ Firestore sync triggered
- ✓ Calendar updated instantly

**Actual Results**:
```
[ ] Pass  [ ] Fail  [ ] Partial
Notes: _________________________________
Database Entry:
  Amount: ________
  Category: ________
  Date: ________
  Type: ________
```

### Test 5.2: Manual Submit (auto_submit: false)
**Setup**: AI returns uncertain response

**Steps**:
1. Send: `"Gì đó lạ lẫm"`
2. AI responds with auto_submit: false
3. Check transaction preview
4. Manually save via UI (test feature later)

**Expected Results**:
- ✓ Response shows transaction data
- ✓ AI asks for confirmation
- ✓ No automatic save
- ✓ User can edit and submit
- ✓ Or dismiss to cancel

**Actual Results**:
```
[ ] Pass  [ ] Fail  [ ] Partial
Notes: _________________________________
```

---

## 🧪 Phase 6: Side-Effects & Stability Tests

### Test 6.1: Existing Features Unaffected
**Setup**: App fully functional before and after AI tests

**Steps**:
1. Before opening AI modal:
   - Verify main screen responsive
   - Check transaction list loads
   - Try manual transaction entry
   - Check calendar interaction

2. After opening AI modal multiple times:
   - Repeat above steps
   - Verify no performance degradation
   - Check no memory leaks

**Expected Results**:
- ✓ All features work identically
- ✓ No FPS drops
- ✓ No navigation issues
- ✓ No data corruption
- ✓ App remains smooth

**Actual Results**:
```
Before AI: [ ] Pass  [ ] Fail
After AI:  [ ] Pass  [ ] Fail
Navigation: [ ] OK  [ ] Issues
Performance: [ ] OK  [ ] Degraded
```

### Test 6.2: UI Layer Isolation
**Setup**: Modal open with AI processing

**Steps**:
1. While modal processing, try:
   - Interact with visible underlying UI (if any)
   - Tap outside modal overlay
   - Use device back button
   - Rotate screen

**Expected Results**:
- ✓ Overlay blocks interaction
- ✓ Tap outside closes modal
- ✓ Back button closes modal
- ✓ Screen rotation handled gracefully
- ✓ State preserved after rotation

**Actual Results**:
```
Overlay blocking: [ ] OK  [ ] Issues
Back button: [ ] OK  [ ] Issues
Rotation: [ ] OK  [ ] Issues
Notes: _________________________________
```

### Test 6.3: Memory & Performance
**Setup**: Device with monitoring tools (optional)

**Steps**:
1. Open DevTools Memory profiler
2. Open/close AI modal 10 times
3. Send 5-10 messages
4. Check heap size
5. Look for memory leaks

**Expected Results**:
- ✓ No memory leak warnings
- ✓ Heap returns to baseline after cleanup
- ✓ Animations smooth (60 fps)
- ✓ No significant heap growth
- ✓ CPU usage normal

**Performance Metrics**:
```
Initial Heap: ________
After 5 opens: ________
After 10 opens: ________
After 10 messages: ________
Final Heap: ________
Leaks Detected: [ ] Yes  [ ] No
```

---

## 🧪 Phase 7: Edge Cases & Robustness

### Test 7.1: Long Messages
**Setup**: Modal open

**Steps**:
1. Type very long message (200+ characters)
2. Send
3. Observe handling

**Expected Results**:
- ✓ Text wraps correctly
- ✓ Send still works
- ✓ Response displays properly
- ✓ Max 500 char limit enforced

**Actual Results**:
```
[ ] Pass  [ ] Fail
Notes: _________________________________
```

### Test 7.2: Rapid Sends
**Setup**: Modal open

**Steps**:
1. Send message
2. Immediately tap send button again (before response)
3. Or send multiple messages quickly

**Expected Results**:
- ✓ Button disabled during processing
- ✓ Queue handled properly
- ✓ All messages processed in order
- ✓ No duplicates

**Actual Results**:
```
[ ] Pass  [ ] Fail
Notes: _________________________________
```

### Test 7.3: Network Interruption
**Setup**: Modal open with active connection

**Steps**:
1. Start sending message
2. Disable network (airplane mode)
3. Observe error handling
4. Re-enable network
5. Try again

**Expected Results**:
- ✓ Clear error message shown
- ✓ No infinite loading
- ✓ Retry possible after reconnect
- ✓ No corrupted state

**Actual Results**:
```
[ ] Pass  [ ] Fail
Notes: _________________________________
```

---

## 📊 Test Summary Report

### Overall Status
```
✓ Rendering: ___/3 tests passed
✓ Interaction: ___/3 tests passed
✓ Input/Messages: ___/4 tests passed
✓ API/Response: ___/3 tests passed
✓ Integration: ___/2 tests passed
✓ Stability: ___/3 tests passed
✓ Edge Cases: ___/3 tests passed

Total: ___/21 tests passed (__%)
```

### Critical Issues Found
```
[ ] None
[ ] 1-2 minor
[ ] 3+ major
[ ] Blocking issues

List: _________________________________
```

### Quality Metrics
```
Code Quality: Pass / Fail
Performance: Pass / Fail
Stability: Pass / Fail
UX: Pass / Fail
Integration: Pass / Fail

Overall Rating: ___/5 Stars
```

### Sign-off
```
Tested By: _____________________
Date: _____________________
Time: _____________________
Device: _____________________
OS Version: _____________________
Build: _____________________
```

---

## 🎯 Next Steps

### If All Tests Pass ✅
- Ready for production deployment
- Update version number
- Create release notes
- Monitor user feedback

### If Issues Found ⚠️
- Document in issue tracker
- Prioritize by severity
- Fix and re-test
- Re-run complete test suite

### Optional Enhancements
- [ ] Setup voice input library
- [ ] Add conversation persistence
- [ ] Implement custom models
- [ ] Add analytics tracking
- [ ] Create admin dashboard

---

**Test Plan Version**: 1.0
**Last Updated**: April 17, 2024
**Total Test Cases**: 21
**Estimated Time**: 30-45 minutes
