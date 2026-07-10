로키가 서든을 안 내줘서 직접 Gemini갈궈서 만들었습니다.

.pyw 확장자로 실행 시 파이썬 및 라이브러리 설치가 필요합니다.

<img width="745" height="916" alt="image" src="https://github.com/user-attachments/assets/d2eb4eb2-2405-4fa1-af60-c046aa30563c" />


.exe 실행 시 다음과 같은 오류가 발생 할 수 있습니다.

<img width="728" height="371" alt="image" src="https://github.com/user-attachments/assets/d64154a1-5dc9-49fd-95ef-b188cb3ae3d0" />

<br><br>

뭘 할 수 있나요?

<img width="120" height="136" alt="image" src="https://github.com/user-attachments/assets/187a7f95-8e7c-4ff0-8054-0b46eebc02f2" />

SuddenOverlay.phw 파일을 오픈하시면 화면 좌상단에 민트색 박스가 나타납니다

<img width="258" height="223" alt="image" src="https://github.com/user-attachments/assets/51c0cc67-8b62-40c7-a68a-729d71a8a8b3" />

해당 박스에 마우스를 올려 우클릭을 하시면 메뉴가 오픈됩니다.

<img width="158" height="147" alt="image" src="https://github.com/user-attachments/assets/c39ccb76-c909-49a7-afe9-ad92a577fad3" />

각각의 메뉴는 다음과 같은 기능을 가집니다.

새 컬러 박스 추가  :  화면 좌상단에 컬러 박스를 생성합니다.

새 그림 추가  :  파일 탐색기를 통하여 오버레이로 띄울 이미지를 선택합니다.

<img width="1173" height="640" alt="image" src="https://github.com/user-attachments/assets/027971cd-cb69-4512-8001-1ccc79313cb0" />

파일은 기본적으로 png, jpg, gif, webp 확장자를 지원합니다.

이 창 색상 변경  :  선택된 창의 채도를 변경합니다.

이 창 투명도 조절  :  선택된 창의 투명도를 조절합니다.

이 창 크기 조절  :  크기 설정 관련 메뉴입니다.

가로/세로 픽셀 직접 입력  :  선택된 창의 크기를 픽셀단위로 조절할 수 있습니다. 비율은 창의 원본 크기 기준입니다.

원본 크기 및 비율로 복구  :  선택된 창의 크기를 원본 크기로 복구합니다.

이 창 지우기  :  선택된 창을 삭제합니다. 원본 이미지는 삭제되지 않습니다.

전체 종료  :  프로그램을 종료합니다.

<br>

이미지, 컬러 박스를 추가, 이동한 흔적이 있다면 동일 경로에 overlay_config.json 파일이 생성됩니다.

해당 파일이 있다면 프로그램 재실행시 종료 전 저장된 위치, 이미지를 가지고옵니다.

오버레이의 on/off 토글키가 있습니다(기본값 F8)

이미지의 테두리를 드래그하여 임의로 크기를 조절할 수 있습니다.

해상도가 너무 큰 png파일, 용량이 큰 gif, webp는 추천하지 않습니다.<br>
해당 이슈로 강제 종료시 overlay_config 파일을 삭제 후 재실행해주세요(초기값으로 설정)

<br>

예시

<img width="2560" height="1440" alt="image" src="https://github.com/user-attachments/assets/dde903d3-f531-4760-a11a-12a81f4aa024" />

<img width="428" height="38" alt="image" src="https://github.com/user-attachments/assets/a89b98a0-8b4f-42af-99f3-fa042cc9dc17" />

위와 같이 셋팅시 약 140mb 메모리 점유율을 나타냅니다. (컬러박스, jpg, gif, webp)
