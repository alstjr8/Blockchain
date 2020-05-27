from flask import Flask, render_template, request, jsonify, make_response
import hashlib
import time
import csv
import random
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
import json
import re
from urllib.parse import parse_qs
from urllib.parse import urlparse
import threading
import cgi
from tempfile import NamedTemporaryFile
import shutil
import requests  # for sending new block to other nodes
import pandas as pd
import uuid
from sqlalchemy import create_engine  # for database connection
from Crypto.PublicKey import RSA  # for rsa verification
from base64 import b64encode, b64decode  # for rsa verification (string public key to public key object)
from multiprocessing import Process, Lock  # for using Lock method(acquire(), release())

# for Put Lock objects into variables(lock)
lock = Lock()

PORT_NUMBER = 8666
g_bcFileName = "blockchain.csv"
g_nodelstFileName = "nodelst.csv"
g_receiveNewBlock = "/node/receiveNewBlock"
g_difficulty = 5
g_maximumTry = 100
g_nodeList = {'trustedServerAddress': '8666'}  # trusted server list, should be checked manually
g_databaseURL = "postgresql://postgres:postgres@localhost:5432/postgres"

app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False

class Blockchain:

    def __init__(self):
        self.blockColumns = ['previous_hash', 'time_stamp', 'tx_data', 'current_hash', 'proof']
        self.blockChain = pd.DataFrame([], columns=self.blockColumns)

    def addBlock(self, block):
        self.blockChain = self.blockChain.append(pd.DataFrame(block, columns=self.blockColumns))
        self.blockChain.reset_index(inplace=True, drop=True)

    def getLatestBlock(self):
        return self.blockChain.iloc[[-1]]

    def generateGenesisBlock(self):
        if not self.blockChain.values.tolist():
            print("generateGenesisBlock is called")
            timestamp = time.time()
            print("time.time() => %f \n" % timestamp)
            tempHash = calculateHash(0, '0', timestamp, "Genesis Block", 0)
            print(tempHash)
            self.blockChain = pd.DataFrame([['0', timestamp, "Genesis Block", tempHash, 0]], columns=self.blockColumns)
            return
        else:
            print("block already exists")
            raise MyException("generateGenesisBlock error, block already exists")

    def readBlockchain(self):
        print("readBlockchain")
        try:
            engine_postgre = create_engine(g_databaseURL)
            query_block = "select " + ",".join(self.blockColumns) + " from bc_blockchain order by index"
            self.blockChain = pd.read_sql_query(query_block, engine_postgre)
            engine_postgre.dispose()
        except:
            raise MyException("Database Connection Failed")

        print("Pulling blockchain from database...")
        if not self.blockChain.values.tolist():
            raise MyException("No Block Exists")
        else:
            return


    def toJSON(self):
        data = []
        block = {}
        for i in range(0, len(self.blockChain)):
            block['index'] = str(self.blockChain.loc[[i]].index[0])
            for j in range(0, 5):
                block[self.blockChain.columns[j]] = str(self.blockChain.loc[i][j])
            data.append(block)
            block = {}
        return data

    def writeBlockchain(self, uuidToUpdate):
        try:
            engine_postgre = create_engine(g_databaseURL)
            for i in range(0, len(self.blockChain)):
                try:
                    self.blockChain.loc[[i]].to_sql(name="bc_blockchain", con=engine_postgre, index=True,
                                                    if_exists="append")
                except:
                    pass

            for uuid in uuidToUpdate:
                update_query = "update bc_tx_pool set commityn=1 where uuid='" + str(uuid) + "'"
                engine_postgre.execute(update_query)

            engine_postgre.dispose()
            print("blockchain written to database")
        except:
            raise MyException("database connection failed.")

    def checkBalance(self, target):
        balance = 0
        for txdata in self.blockChain['tx_data'].values.tolist():
            txlist = txdata.split(" |")
            for tx in txlist:
                if tx != '' and tx != 'Genesis Block':
                    sender = tx.split(", ")[1]
                    amount = tx.split(", ")[2]
                    receiver = tx.split(", ")[3]
                    fee = tx.split(", ")[4]
                    if sender == target:
                        balance -= float(amount) + float(fee)
                    if receiver == target:
                        balance += float(amount)
        return balance


class Block:

    def __init__(self, index, previousHash, timestamp, data, currentHash, proof):
        self.index = index
        self.previousHash = previousHash
        self.timestamp = timestamp
        self.data = data
        self.currentHash = currentHash
        self.proof = proof

    def toJSON(self):
        return json.dumps(self, default=lambda o: o.__dict__, sort_keys=True, indent=4)


class txDataList:

    def __init__(self):
        self.txColumns = ['commityn', 'sender', 'amount', 'receiver', 'fee', 'uuid', 'tx_data', 'signature']
        self.txDataFrame = pd.DataFrame([], columns=self.txColumns)

    def toList(self):
        return self.txDataFrame.values.tolist()

    def addTxData(self, txList):
        txdataframe = pd.DataFrame(txList, columns=self.txColumns)
        self.txDataFrame = self.txDataFrame.append(txdataframe)

    def writeTx(self):
        try:
            engine_postgre = create_engine(g_databaseURL)
        except:
            raise MyException("declined : database connection failed")

        try:
            self.txDataFrame.to_sql(name="bc_tx_pool", con=engine_postgre, index=False, if_exists="append")
            engine_postgre.dispose()
        except:
            raise MyException("database write error, maybe same uuid already exists")
        else:
            print('txData written to database')
            return

class MyException(Exception):
    def __init__(self, msg):
        self.msg = msg

    def __str__(self):
        return self.msg


def signTx(sender_prvKeyString, receiver_pubKeyString, amount, fee, uuidString):
    try:
        sender_prvKey = RSA.importKey(b64decode(sender_prvKeyString))  # sender 공개키가 유효한지 검증
        RSA.importKey(b64decode(receiver_pubKeyString))   # receiver 공개키가 유효한지 검증
        msg = sender_prvKeyString + receiver_pubKeyString + amount + fee + uuidString
        msgHash = hashlib.sha256(msg.encode('utf-8')).digest()
    except:
        raise MyException("key is not valid")
    return sender_prvKey.sign(msgHash,'')[0]


def calculateHash(index, previousHash, timestamp, data, proof):
    value = str(index) + str(previousHash) + str(timestamp) + str(data) + str(proof)
    sha = hashlib.sha256(value.encode('utf-8'))
    return str(sha.hexdigest())


def calculateHashForBlock(block):
    return calculateHash(block.index, block.previousHash, block.timestamp, block.data, block.proof)


def getTxData(miner):
    try:
        engine_postgre = create_engine(g_databaseURL)
        tx_query = "SELECT uuid, tx_data FROM bc_tx_pool WHERE commityn = 0 order by fee desc limit 5"
        tx_df = pd.read_sql_query(tx_query, engine_postgre)
        engine_postgre.dispose()
    except:
        raise MyException("Database Connection Failed")

    totalfee = 0
    for tx in tx_df['tx_data'].values.tolist():
        totalfee += float(tx.replace(" |", "").split(", ")[4])

    strTxData = str(uuid.uuid4()) + ", MiningReward, " + str(100 + totalfee) + ", " + str(miner) + ", 0 |"
    for tx in tx_df['tx_data'].values.tolist():
        strTxData += tx

    else:
        if strTxData == '':
            raise MyException('No TxData Found, Mining aborted')
        return strTxData, tx_df['uuid'].values.tolist()


def mine(miner):
    # TODO blockchain validation, tx pool validation

    blockchain = Blockchain()

    try:
        strTxData, uuidToUpdate = getTxData(miner)
    except:
        raise

    try:
        blockchain.readBlockchain()
    except MyException as error:
        if str(error) == "No Block Exists":
            try:
                blockchain.generateGenesisBlock()
            except:
                raise
        else:
            raise

    t = threading.Thread(target=mineNewBlock, args=[blockchain, strTxData, uuidToUpdate])
    t.start()

    return 0


def mineNewBlock(blockchain, strTxData, uuidToUpdate, difficulty=g_difficulty):

    previousBlock = blockchain.getLatestBlock()
    nextIndex = previousBlock.index[0] + 1
    prevHash = previousBlock['current_hash'].array[0]
    time.sleep(0.01)  # genesis block 이랑 2번째 block 이랑 timestamp 가 같길래 0.01초라도 다르게 하려고
    timestamp = time.time()
    proof = 0
    newBlockFound = False

    print('Mining a block...')

    while not newBlockFound:
        nextHash = calculateHash(nextIndex, prevHash, timestamp, strTxData, proof)
        if nextHash[0:difficulty] == '0' * difficulty:
            stopTime = time.time()
            timer = stopTime - timestamp
            print('New block found with proof', proof, 'in', round(timer, 2), 'seconds.')
            newBlockFound = True
        else:
            proof += 1
            if(proof % 100000 == 0):
                print(proof)

    blockchain.addBlock([[prevHash, timestamp, strTxData, nextHash, proof]])
    try:
        blockchain.writeBlockchain(uuidToUpdate)
    except Exception as error:
        print(error)


def isSameBlock(block1, block2):
    if str(block1.index) != str(block2.index):
        return False
    elif str(block1.previousHash) != str(block2.previousHash):
        return False
    elif str(block1.timestamp) != str(block2.timestamp):
        return False
    elif str(block1.data) != str(block2.data):
        return False
    elif str(block1.currentHash) != str(block2.currentHash):
        return False
    elif str(block1.proof) != str(block2.proof):
        return False
    return True


def isValidNewBlock(newBlock, previousBlock):
    if int(previousBlock.index) + 1 != int(newBlock.index):
        print('Indices Do Not Match Up')
        return False
    elif previousBlock.currentHash != newBlock.previousHash:
        print("Previous hash does not match")
        return False
    elif calculateHashForBlock(newBlock) != newBlock.currentHash:
        print("Hash is invalid")
        return False
    elif newBlock.currentHash[0:g_difficulty] != '0' * g_difficulty:
        print("Hash difficulty is invalid")
        return False
    return True


def validateTx(txToMining):
    try:
        publicKey = RSA.importKey(b64decode(txToMining['sender']))  # sender 는 공개키(string), 문자열을 공개키 객체로 바꾸는중
        RSA.importKey(b64decode(txToMining['receiver']))  # 받는사람 주소가 유효한 공개키가 아닐시 except 로 처리
    except ValueError:
        raise MyException("declined : key is not valid")

    try:
        tx = str(txToMining['sender']) + str(txToMining['receiver']) + "%f" % float(
            txToMining['amount']) + "%f" % float(txToMining['fee']) + str(txToMining['uuid'])
        tx = tx.replace("\n", "")
        if ", " in tx or "| " in tx:  # 블록 txData split 할 때 쓸거라서 여기 있으면 안됨
            raise
        txHash = hashlib.sha256(tx.encode('utf-8')).digest()  # 보낼 때 sign 한 문자열의 해쉬값
        if not publicKey.verify(txHash, (int(txToMining['signature']),)):  # 보낸사람의 public key 로 검증
            raise MyException("declined : sign does not match") # verify 가 false 일 시 오류발생
    except ValueError:
        raise MyException("declined : amount or fee is not a number") # 형변환 실패시 오류발생
    except Exception:
        raise MyException("declined : validation failed")


def newtx(txToMining):
    newTxData = txDataList()

    try:
        sender_prvKeyString = request.form['sender'].replace('-----BEGIN RSA PRIVATE KEY-----', '').replace(
            '-----END RSA PRIVATE KEY-----', '').replace('\n', '')
        sender_pubKey = RSA.importKey(b64decode(sender_prvKeyString)).publickey()
        sender_pubKeyString = b64encode(sender_pubKey.exportKey('DER')).decode('utf-8')
    except ValueError:
        raise MyException("declined : key is not valid")

    try:
        validateTx(txToMining)
    except Exception:
        raise
    else:
        tx = [[0, sender_pubKeyString, float(txToMining['amount']), txToMining['receiver'], float(txToMining['fee']),
               txToMining['uuid']]]
        tx[0].append(
            txToMining['uuid'] + ", " + sender_pubKeyString + ", " + str(txToMining['amount']) + ", " + txToMining[
                'receiver'] + ", " + str(txToMining['fee']) + " |")
        tx[0].append(txToMining['signature'])
        newTxData.addTxData(tx)

    try:
        newTxData.writeTx()
    except Exception:
        raise


def isValidChain(bcToValidate):
    genesisBlock = []
    bcToValidateForBlock = []

    # Read GenesisBlock
    try:
        with open(g_bcFileName, 'r', newline='') as file:
            blockReader = csv.reader(file)
            for line in blockReader:
                block = Block(line[0], line[1], line[2], line[3], line[4], line[5])
                genesisBlock.append(block)
    #                break
    except:
        print("file open error in isValidChain")
        return False

    # transform given data to Block object
    for line in bcToValidate:
        # print(type(line))
        # index, previousHash, timestamp, data, currentHash, proof
        block = Block(line['index'], line['previousHash'], line['timestamp'], line['data'], line['currentHash'],
                      line['proof'])
        bcToValidateForBlock.append(block)

    # if it fails to read block data  from db(csv)
    if not genesisBlock:
        print("fail to read genesisBlock")
        return False

    # compare the given data with genesisBlock
    if not isSameBlock(bcToValidateForBlock[0], genesisBlock[0]):
        print('Genesis Block Incorrect')
        return False

    # tempBlocks = [bcToValidateForBlock[0]]
    # for i in range(1, len(bcToValidateForBlock)):
    #    if isValidNewBlock(bcToValidateForBlock[i], tempBlocks[i - 1]):
    #        tempBlocks.append(bcToValidateForBlock[i])
    #    else:
    #        return False

    for i in range(0, len(bcToValidateForBlock)):
        if isSameBlock(genesisBlock[i], bcToValidateForBlock[i]) == False:
            return False

    return True


# 20190605 / (YuRim Kim, HaeRi Kim, JongSun Park, BohKuk Suh , HyeongSeob Lee, JinWoo Song)
# /* addNode function Update */
# If the 'nodeList.csv' file is already open, make it inaccessible via lock.acquire()
# After executing the desired operation, changed to release the lock.(lock.release())
# Reason for time.sleep ():
# prevents server overload due to repeated error message output and gives 3 seconds of delay to allow time for other users to wait without opening file while editing and saving csv file.
# Removed temp files to reduce memory usage and increase work efficiency.
def addNode(queryStr):
    # save
    previousList = []
    nodeList = []
    nodeList.append([queryStr[0], queryStr[1], 0])  # ip, port, # of connection fail

    try:
        with open(g_nodelstFileName, 'r', newline='') as csvfile:
            reader = csv.reader(csvfile)
            for row in reader:
                if row:
                    if row[0] == queryStr[0] and row[1] == queryStr[1]:
                        print("requested node is already exists")
                        csvfile.close()
                        nodeList.clear()
                        return -1
                    else:
                        previousList.append(row)

            openFile3 = False
            while not openFile3:
                lock.acquire()
                try:
                    with open(g_nodelstFileName, 'w', newline='') as csvfile:
                        writer = csv.writer(csvfile)
                        writer.writerows(nodeList)
                        writer.writerows(previousList)
                        csvfile.close()
                        nodeList.clear()
                        lock.release()
                        print('new node written to nodelist.csv.')
                        return 1
                except Exception as ex:
                    print(ex)
                    time.sleep(3)
                    print("file open error")
                    lock.release()

    except:
        # this is 1st time of creating node list
        try:
            with open(g_nodelstFileName, "w", newline='') as file:
                writer = csv.writer(file)
                writer.writerows(nodeList)
                nodeList.clear()
                print('new node written to nodelist.csv.')
                return 1
        except Exception as ex:
            print(ex)
            return 0


def readNodes(filePath):
    print("read Nodes")
    importedNodes = []

    try:
        with open(filePath, 'r', newline='') as file:
            nodeReader = csv.reader(file)
            for row in nodeReader:
                line = [row[0], row[1]]
                importedNodes.append(line)
        print("Pulling txData from csv...")
        return importedNodes
    except:
        return []


def broadcastNewBlock(blockchain):
    # newBlock  = getLatestBlock(blockchain) # get the latest block
    importedNodes = readNodes(g_nodelstFileName)  # get server node ip and port
    reqHeader = {'Content-Type': 'application/json; charset=utf-8'}
    reqBody = []
    for i in blockchain:
        reqBody.append(i.__dict__)

    if len(importedNodes) > 0:
        for node in importedNodes:
            try:
                URL = "http://" + node[0] + ":" + node[1] + g_receiveNewBlock  # http://ip:port/node/receiveNewBlock
                res = requests.post(URL, headers=reqHeader, data=json.dumps(reqBody))
                if res.status_code == 200:
                    print(URL + " sent ok.")
                    print("Response Message " + res.text)
                else:
                    print(URL + " responding error " + res.status_code)
            except:
                print(URL + " is not responding.")
                # write responding results
                tempfile = NamedTemporaryFile(mode='w', newline='', delete=False)
                try:
                    with open(g_nodelstFileName, 'r', newline='') as csvfile, tempfile:
                        reader = csv.reader(csvfile)
                        writer = csv.writer(tempfile)
                        for row in reader:
                            if row:
                                if row[0] == node[0] and row[1] == node[1]:
                                    print("connection failed " + row[0] + ":" + row[1] + ", number of fail " + row[2])
                                    tmp = row[2]
                                    # too much fail, delete node
                                    if int(tmp) > g_maximumTry:
                                        print(row[0] + ":" + row[
                                            1] + " deleted from node list because of exceeding the request limit")
                                    else:
                                        row[2] = int(tmp) + 1
                                        writer.writerow(row)
                                else:
                                    writer.writerow(row)
                    shutil.move(tempfile.name, g_nodelstFileName)
                    csvfile.close()
                    tempfile.close()
                except:
                    print("caught exception while updating node list")


def row_count(filename):
    try:
        with open(filename) as in_file:
            return sum(1 for _ in in_file)
    except:
        return 0


def compareMerge(bcDict):
    #TODO:제네시스블록 같은지 비교
    #TODO:validate Whole block

     if len(heldBlockchain.blockChain)>=len(bcDict):
        print("maintain the block")
    elif len(heldBlockchain.blockChain)<len(bcDict):
        try :
            engine_postgre = create_engine(g_databaseURL)
            truncate_block = "truncate table bc_blockchain" # SELECT * FROM TABLENAME , TRUNCATE TABLE tablename
            self.blockChain = pd.read_sql_query(truncate_block, engine_postgre)
            engine_postgre.dispose()
            strTxData, uuidToUpdate = getTxData()
            heldBlockchain.writeBlockchain(uuidToUpdate)

            for line in tempDict:    
                heldBlockchain.addBlock([[line['previous_hash'], line['time_stamp'], line['tx_data'], line['current_hash'],
                      line['proof']])
            #db에 block 정보 넣기

        except:
            print("database error")

            
@app.route('/main')
def main_route():
    return render_template('main.html')


@app.route('/sign', methods=['POST'])
def sign_route():
    data = {}
    sender_prvKeyString = str(request.form['sender']).replace('-----BEGIN RSA PRIVATE KEY-----', '').replace(
        '-----END RSA PRIVATE KEY-----', '').replace('\n', '')
    receiver_pubKeyString = str(request.form['receiver']).replace('-----BEGIN PUBLIC KEY-----', '').replace(
        '-----END PUBLIC KEY-----', '').replace('\n', '')
    try:
        amount = "%f" % float(request.form['amount'])
        fee = "%f" % float(request.form['fee'])
    except ValueError:
        msg = "Failed : amount or fee is not a number"
        return {"msg": msg}

    if float(amount) < 0 or float(fee) < 0:
        msg = "Failed : amount or fee cannot be lower than 0"
        return {"msg": msg}

    if float(amount) == 0:
        msg = "Failed : amount cannot be 0"
        return {"msg": msg}

    uuidString = str(uuid.uuid4())
    try:
        signature = signTx(sender_prvKeyString, receiver_pubKeyString, amount, fee, uuidString)
    except MyException as error:
        print(error)
        data['msg'] = str(error)
    else:
        data = make_response({"sender": request.form['sender'],
                "receiver": request.form['receiver'],
                "amount": request.form['amount'],
                "fee": request.form['fee'],
                "uuid": uuidString,
                "signature": str(signature),
                "msg": "signed!"})
    finally:
        resp = make_response(data)
        return resp


@app.route('/validateSign', methods=['POST'])
def validateSign_route():
    sender_prvKeyString = str(request.form['sender']).replace('-----BEGIN RSA PRIVATE KEY-----', '').replace(
        '-----END RSA PRIVATE KEY-----', '').replace('\n', '')
    receiver_pubKeyString = str(request.form['receiver']).replace('-----BEGIN PUBLIC KEY-----', '').replace(
        '-----END PUBLIC KEY-----', '').replace('\n', '')
    try:
        amount = "%f" % float(request.form['amount'])
        fee = "%f" % float(request.form['fee'])
    except ValueError as error:
        print(error)
        return {"validity": "sign is invalid, amount or fee is not a number"}

    try:
        uuidString = str(request.form['uuid'])
        signToValidate = request.form['signature']
        signature = signTx(sender_prvKeyString, receiver_pubKeyString, amount, fee, uuidString)
    except Exception as error:
        print(error)
        return {"validity": "sign is invalid, abnormal key data"}

    if(signToValidate == str(signature)):
        validity = "sign is valid"
    elif(signToValidate == ''):
        validity = "sign is invalid, no sign data"
    else:
        validity = "sign is invalid, sign does not match"

    resp = make_response({"validity": validity})
    return resp


@app.route('/getPrivateKey')
def getPrivateKey_route():
    privateKey = RSA.generate(1024)
    resp = make_response(b64encode(privateKey.exportKey('DER')).decode('utf-8'))
    return resp

@app.route('/getPublicKey')
def getPublicKey_route():
    privateKey = RSA.generate(1024)
    resp = make_response(b64encode(privateKey.publickey().exportKey('DER')).decode('utf-8'))
    return resp


@app.route('/block/getBlockData')
def getBlockData_route():
    # TODO: range return (~/block/getBlockData?from=1&to=300)
    # queryString = urlparse(self.path).query.split('&')
    data = ""  # response json data
    blockchain = Blockchain()

    try:
        blockchain.readBlockchain()
    except MyException as error:
        print(error)
        data = str(error)
    except Exception as error:
        print(str(error))
        data = "Internal Server Error"
    else:
        data = blockchain.toJSON()
    finally:
        resp = make_response(jsonify(data))
        return resp


@app.route('/block/generateBlock', methods=['POST'])
def generateBlock_route():
    data = {}  # response json data
    try:
        miner_prvKeyString = request.form['miner'].replace('-----BEGIN RSA PRIVATE KEY-----', '').replace(
            '-----END RSA PRIVATE KEY-----', '').replace('\n', '')
        miner_pubKey = RSA.importKey(b64decode(miner_prvKeyString)).publickey()
        miner_pubKeyString = b64encode(miner_pubKey.exportKey('DER')).decode('utf-8')
    except Exception as error:
        print(error)
        data['msg'] = "private key is not valid"
        resp = make_response(data)
        return resp

    try:
        mine(miner_pubKeyString)
    except MyException as error:
        print(error)
        data['msg'] = (str(error))
    else:
        data['msg'] = "mining is underway:check later by calling /block/getBlockData"
    finally:
        resp = make_response(data)
        return resp


@app.route('/block/newtx', methods=['POST'])
def newtx_route():
    data = {}
    blockchain = Blockchain()

    try:
        sender_prvKeyString = request.form['sender'].replace('-----BEGIN RSA PRIVATE KEY-----', '').replace(
            '-----END RSA PRIVATE KEY-----', '').replace('\n', '')
        sender_pubKey = RSA.importKey(b64decode(sender_prvKeyString)).publickey()
        sender_pubKeyString = b64encode(sender_pubKey.exportKey('DER')).decode('utf-8')
        payment = float(request.form['amount']) + float(request.form['fee'])
    except Exception as error:
        print(error)
        data['msg'] ="declined : abnormal data."
        resp = make_response(data)
        return resp

    tempDict = request.form
    try:
        blockchain.readBlockchain()
        if blockchain.checkBalance(sender_pubKeyString) < payment:
            raise MyException(
                "declined : There is not enough bitTokens in your wallet. Mine new blocks to make bitTokens.")
        newtx(tempDict)
    except MyException as error:
        print(error)
        data['msg'] = str(error)
    else:
        data['msg'] = "accepted : it will be mined later"
    finally:
        resp = make_response(data)
        return resp


@app.route('/checkBalance', methods=['POST'])
def checkBalance_route():
    data = {}
    blockchain = Blockchain()

    try:
        sender_prvKeyString = request.form['sender'].replace('-----BEGIN RSA PRIVATE KEY-----', '').replace(
            '-----END RSA PRIVATE KEY-----', '').replace('\n', '')
        sender_pubKey = RSA.importKey(b64decode(sender_prvKeyString)).publickey()
        sender_pubKeyString = b64encode(sender_pubKey.exportKey('DER')).decode('utf-8')
    except Exception as error:
        print(error)
        data['msg'] = "declined : abnormal data."
        resp = make_response(data)
        return resp

    try:
        blockchain.readBlockchain()
        data['msg'] = "You have " + str(blockchain.checkBalance(sender_pubKeyString)) + " bitTokens in your wallet."
    except MyException as error:
        print(error)
        data['msg'] = str(error)
    finally:
        resp = make_response(data)
        return resp


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)