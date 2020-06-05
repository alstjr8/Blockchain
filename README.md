# Blockchain
• Collaborator: 김민석, 김보현, 박정근, 이상민

## 목적
• ToyProject용 블록체인 기본 로직 리팩토링 및 추가 구현

## 개요

https://user-images.githubusercontent.com/62678705/83835549-06a38200-a72c-11ea-9bff-b3d489bcdf9f.png

• 전체 구성 

• 개발 환경

• 코드 리팩토링

• 추가 구현

• 보완 사항

## 전체 구성
• 블록체인, 거래 정보 DB 저장

• 웹을 통한 비트코인 거래

• Flask를 통한 Rest API 서버 구축

그림 추가
## 개발 환경
• 운영체제: Window 10

• 개발언어
  - Pycharm
  - MySQL
  - Flask
  - JavaScript

## 코드 리팩토링
• 클래스화
  |Before||After|
  |-|:-:|-|
  |기존의 하나의 블록 객체|→|전체블록이 포함된 블록체인 클래스 생성|
  |기존의 트랜잭션 데이터 객체|→|클래스화하여 트랜잭션 풀 구현|
  |노드 리스트|→|클래스화|

• 예외처리
  |Before||After|
  |-|:-:|-|
  |return value를 통한 예외 처리|→|새로운 예외처리 클래스 생성|
  |Rest API에서 예외 처리|→|raise를 활용하여 예외가 발생한 부분에서 예외 처리|

• mine함수 구현
  |Before||After|
  |-|:-:|-|
  |바로 mineNewBlock 함수 호출|→|새로운 블록 채굴을 위한 준비(readBlockchian & getTxData)|
  |threading mine function|→|threading mineNewBlock function|
  
## 추가 구현
• Flask
  |Before||After|
  |-|:-:|-|
  |Socket Server|→|Flask를 활용한 Rest API 서버 구축|
  |url pattern을 찾아 GET, POST 구별|→|@app.route를 통해 url을 함수와 매치|

• Web(JavaScript)
  - user가 서버로부터 개인키, 공개키를 생성받아 전자서명을 통한 비트코인 거래.
  - user가 블록 채굴.
  - user가 블록 정보를 얻을 수 있음.
  
• PostgreSQL
  |Before||After|
  |-|:-:|-|
  |기존의 csv 파일 관리|→|관계형 데이터베이스를 통한 효율적인 블록체인, 거래 데이터 관리|
  
  - DB 테이블 정의서
  
    i) Blockchian
      |구성자료명|컬럼헤더명|자료형태|PK|설명|
      |------|---|---|:---:|---|
      |블록번호|index|숫자|-|블록번호|
      |이전블록 해시|previous_hash|문자열|-|이전블록 해시값|
      |블록 생성 시간|time_stamp|문자열|-|블록 생성 시간|
      |거래 데이터|tx_data|문자열|-|5개의 거래 데이터 합|
      |현재블록 해시|current_hash|문자열|1|현재블록 해시값|
      |작업증명|proof|문자열|-|작업증명 횟수|

    ii) Transaction Pool
      |구성자료명|컬럼헤더명|자료형태|PK|설명|
      |------|---|---|:---:|---|
      |블록체인 포함 여부|commitYN|문자열|-|블록체인 포함 여부|
      |송금자|sender|문자열|-|송금자 정보|
      |거래량|amount|숫자|-|비트코인 거래량|
      |수신자|receiver|문자열|-|수신자 정보|
      |수수료|fee|숫자|-|수수료|
      |고유번호|uuid|문자열|1|고유번호|
      |거래내역|tx_data|문자열|-|거래내역|
      |전자서명|signiture|문자열|-|전자서명|

    iii) NodeList
      |구성자료명|컬럼헤더명|자료형태|PK|설명|
      |------|---|---|:---:|---|
      |IP|ip|문자열|1|전자서명|
      |Port|port|문자열|1|노드 포트번호|
      |The count of not responding|tmp|숫자|-|responding하지 않는 횟수|

• 전자서명
  - RSA 암호화 방식을 통한 비트코인 전자서명 구현
  - 비트코인 거래 시 송금자가 송금자의 개인키로 전자서명 후 송금자의 공개키로 거래 유효성 검증
그림 추가

## 보완사항
• merkle root 구현
