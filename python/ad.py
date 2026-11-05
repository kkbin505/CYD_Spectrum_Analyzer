import msvcrt
import time
import math
from ctypes import *
# 注意：由于本demo调用msvcrt.kbhit()来获取空格中止循环，需选中Run/ Configurations中的Emulate terminal in output console设置复选框
# 本demo示例64位调用方式，需要32位调用时将x64->x86
pDll = CDLL("../../BIN/x64/USB2406.dll")

ADChStart = c_byte(0)  # 通道选择首通道
ADChCount = c_byte(4)  # 通道选择通道数
FreqMode = c_uint(0)  # 分频模式
ADFreq = c_float(100)  # 采样频率，单位KHz
pADFreq = POINTER(c_float)(ADFreq)
ADTrig = c_int(1)  # 触发源
ADTrigSource = c_int(0)  # 触发方式
ADTrigDirec = c_int(1)  # 触发方向
ADTrigVol = c_float(2)  # 触发电压
ADGain = c_uint16(0)  # 增益（各通道可任意设置增益，本demo简化为所有通道统一配置）
ADPreLength = c_int(0)  # 预采点数
bState = c_int(0)  # 恒流源
ADcal = c_int(0)  # 校准

karray = c_int * 10
kValue = karray()
barray = c_int * 10
bValue = barray()


# ------------------------------------- 设置AD参数 -------------------------------------
def SetADPara():
    # bVal = []
    bvctarray = c_int16 * 2
    bvctTmp = bvctarray()
    # bvctTmp = []
    count = 0
    num = 0

    print("AD采集默认参数设置如下：")
    while 1:
        print("\n")
        if ADChStart.value+ADChCount.value > 4:
            ADChCount.value = 4 - ADChStart.value
        print("AD起始通道：%d" % ADChStart.value)
        print("通道数：%d" % ADChCount.value)

        print("分频模式：", end='')
        if FreqMode.value == 0:
            print("ad7765(1～156KHz)")
        else:
            print("ad7764(1～312KHz)")
        print("采样率(KHz)：%f" % ADFreq.value)

        print("触发源：", end='')
        if ADTrig.value == 0:
            print("外触发")

            print("触发方式：", end='')
            if ADTrigSource.value == 0:
                print("模拟触发")
            else:
                print("数字触发")

            print("触发电压：%f" % ADTrigVol.value)

            print("触发方向：", end='')
            if ADTrigDirec.value == 0:
                print("上升沿触发")
            elif ADTrigDirec.value == 1:
                print("下降沿触发")
            else:
                print("电平触发")

            print("预采集点数：%d" % ADPreLength.value)

        else:
            print("软触发")

        print("增益：", end='')
        if ADGain.value == 0:
            print("±10V")
        elif ADGain.value == 1:
            print("±1V")
        elif ADGain.value == 2:
            print("±100mV")
        else:
            print("±10mV")

        print("恒流源：", end='')
        if bState.value == 0:
            print("不开启")
        else:
            print("开启")

        print("校准：", end='')
        if ADcal.value == 0:
            print("不开启")
        else:
            print("开启")

        time.sleep(0.1)
        ijudge = input("是否修改以上参数(0--否，1--是):")
        # msvcrt.getch()
        if ijudge == "1":
            ijudge = input("修改项(0--起始通道，1--通道数，2--分频模式，3--采样率，4--触发源，5--量程，6--恒流源，7--校准):")
            # msvcrt.getch()
            if ijudge == "0":
                ADChStart.value = int(input("AD起始通道(0~3)："))
                # msvcrt.getch()
            elif ijudge == "1":
                ADChCount.value = int(input("通道数(1~4)："))
                # msvcrt.getch()
            elif ijudge == "2":
                FreqMode.value = int(input("分频模式(0--1～156KHz，1--1~312KHz)："))
                # msvcrt.getch()
            elif ijudge == "3":
                ADFreq.value = float(input("采样率(KHz)"))
                # msvcrt.getch()
            elif ijudge == "4":
                ADTrig.value = int(input("触发源(0--外触发，1--软触发)："))
                # msvcrt.getch()
                if ADTrig.value == 0:
                    ijudge = input("0--触发方式，1--触发方向，2--预采集点数：")
                    # msvcrt.getch()
                    if ijudge == "0":
                        ADTrigSource.value = int(input("触发方式(0--模拟触发，1--数字触发)："))
                        # msvcrt.getch()
                        if ADTrigSource.value == 0:
                            ADTrigVol.value = float(input("触发电压(-5V ~ 5V)"))
                            # msvcrt.getch()
                    elif ijudge == "1":
                        ADTrigDirec.value = int(input("触发方向(0--上升沿触发，1--下降沿触发，2--电平触发)："))
                        # msvcrt.getch()
                    elif ijudge == "2":
                        ADPreLength.value = int(input("预采集点数(4~2000)(为防止串通道，预采点数需为通道数整数倍)："))
                        # msvcrt.getch()
            elif ijudge == "5":
                ADGain.value = int(input("增益(0--±10V，1--±1V，2--±100mV，3--±10mV)："))
                # msvcrt.getch()
            elif ijudge == "6":
                bState.value = int(input("恒流源(0--不开启，1--开启)："))
                # msvcrt.getch()
            elif ijudge == "7":
                ADcal.value = int(input("校准(0--不开启，1--开启)："))
                # msvcrt.getch()
                if ADcal.value == 1:
                    kb = c_byte * 20
                    kbVal = kb()
                    iResult = pDll.USB2406_RWEEp(int(icard), 0X1000, 20, kbVal, 1)
                    if iResult != 1:
                        print("读取校准参数失败")
                    else:
                        for i in range(0, 20):
                            i = i
                            if i % 5 == 0 and kbVal[i] == 1:
                                for j in range(1, 4, 2):
                                    m = c_uint16(kbVal[j+i])
                                    n = c_uint16(kbVal[j+1+i])
                                    bvctTmp[count] = kbVal[j+i] & 0xff + ((kbVal[j+1+i] & 0xff) << 8)
                                    h = bvctTmp[count]
                                    count = count + 1
                                kValue[num] = bvctTmp[0]
                                bValue[num] = bvctTmp[1]
                                num = num + 1
                                count = 0
        else:
            break
    # 返回值	配置AD采样频率	拨码ID  分频模式   返回AD采样频率
    iResult = pDll.USB2406_SetFreDiv_2(int(icard), FreqMode.value, pADFreq)
    print("实际采样频率%fKHz" % ADFreq.value)

    gain = c_byte * 4
    pGain = gain()
    for i in range(0, 4):
        pGain[i] = ADGain.value
    # 返回值	配置AD增益     拨码ID  增益
    iResult = pDll.USB2406_Set_Gain(int(icard), pGain)

    ADTrig.value = ADTrig.value + ((ADTrigDirec.value + 1) << 1)
    # 返回值	配置AD触发方式	    拨码ID   触发方式
    iResult = pDll.USB2406_SetADMode(int(icard), ADTrig)

    if (ADTrig.value & 0x01) == 0:  # 外触发
        # 返回值	配置AD触发电压	    拨码ID  触发电压
        iResult = pDll.USB2406_Set_Trigger_V(int(icard), ADTrigVol)

        Num = int(int(ADPreLength.value) / int(ADChCount.value))
        # 返回值	配置AD预采集	拨码ID   AD通道数         预采集长度
        iResult = pDll.USB2406_SetADHead(int(icard), ADChCount.value, Num)

        # 返回值	配置AD外触发源	      拨码ID     外触发源
        iResult = pDll.USB2406_SetADTrigSource(int(icard), ADTrigSource)

    chSel = c_byte(0)
    for i in range(ADChStart.value, ADChStart.value + ADChCount.value):
        chSel.value = chSel.value + (1 << i)
    # 返回值  配置AD通道选择  拨码ID  所选通道
    iResult = pDll.USB2406_SetADCh(int(icard), chSel)

    # 返回值	配置AD恒流源	                拨码ID     开启/关闭
    iResult = pDll.USb2406_Set_ConstantVolSource(int(icard), bState)

    # 返回值	清缓存	      拨码ID
    iResult = pDll.USB2406_CLRRAM(int(icard))

    # 返回值	   发送USB请求命令	       拨码ID 0XB2命令
    iResult = pDll.USB2406_IOCTL_VENDOR_REQUEST(int(icard), 0xB2)

    # 返回值	配置AD启动	  拨码ID
    iResult = pDll.USB2406_ADStart(int(icard))


# ------------------------------------- AD采集 -------------------------------------
def ADWork():
    nByte = c_long(0)
    pByte = POINTER(c_long)(nByte)

    if (ADTrig.value & 0x01) == 0:  # 外触发
        if ADTrigSource.value == 1:
            print("配置成功，等待触发信号……")
        else:
            print("配置成功，2s后通过指定卡配置模拟外触发信号……")
            # time.sleep(2)
            dodata = c_byte(1)
            pDodata = POINTER(c_byte)(dodata)
            # 返回值 模拟外触发信号	拨码ID	高电平
            iResult = pDll.USB2406_DO(int(icard), pDodata)
            time.sleep(1)
            dodata.value = 0
            # 返回值 模拟外触发信号	拨码ID	高电平
            iResult = pDll.USB2406_DO(int(icard), pDodata)
            time.sleep(1)
            dodata.value = 1
            # 返回值 模拟外触发信号	拨码ID	高电平
            iResult = pDll.USB2406_DO(int(icard), pDodata)
            print("配置模拟外触发信号完成……")

    Status = c_byte(1)
    pStatus = POINTER(c_byte)(Status)

    dfret = c_double(0.0)
    pDfret = POINTER(c_double)(dfret)

    BufferSize = ADChCount.value * 1024
    barray = c_uint8 * (2*1024*1024*2)
    buffer = barray()
    while 1:
        if msvcrt.kbhit():
            if ord(msvcrt.getch()) == 32:
                break
        # 返回值	获取fifo状态		拨码ID	返回FIFO状态
        iResult = pDll.USB2406_ReadDramState(int(icard), pStatus)
        if Status.value == 6:
            print("fifo溢出")
        elif Status.value == 2:
            # 返回值	获取USB块读数据		 拨码ID	  数据数组 读取长度   实际读取长度
            iResult = pDll.USB2406_IOCTL_BULK_READ(int(icard), buffer, BufferSize, pByte)
            for i in range(0, ADChCount.value):
                if ADcal.value == 0:
                    kVal = 1.0
                    bVal = 0.0
                else:
                    kVal = kValue[i] / 10000.0
                    bVal = bValue[i] / 10000.0

                lbyte = float(buffer[4 * i + 1])
                mbyte = float(buffer[4 * i + 2])
                hbyte = float(buffer[4 * i + 3])
                dfret.value = lbyte + mbyte * 256 + hbyte * 65536
                iResult = pDll.USB2406_Fun_DataToV(pDfret, ADGain)
                x0 = float(math.pow(10.0, ADGain.value))
                # dfret.value = (2.4 * x0 *kVal+bVal)/x0
                dfret.value = (dfret.value * x0 * kVal + bVal) / x0
                print("%12f" % dfret.value, end='')

            print("")

    # 返回值	AD停止		拨码ID
    iResult = pDll.USB2406_ADStop(int(icard))
    # 返回值	清FIFO		 拨码ID
    iResult = pDll.USB2406_CLRRAM(int(icard))


# ------------------------------------- 打开卡 -------------------------------------

hDevice = c_int(0)
phDevice = POINTER(c_int)(hDevice)
# 打开卡
icard = input("需控制打开的拨码ID号[0~15]：")
# msvcrt.getch()
# 返回值	    打开指定卡		        拨码ID     返回句柄
iResult = pDll.USB2406_OpenDevice(int(icard), phDevice)
if iResult == 1:
    print("已打开ID拨码为", int(icard), "的卡，句柄", hDevice.value, "。")

    # -------------------------------------AD-----------------------------------------
    # 返回值	AD停止		拨码ID
    iResult = pDll.USB2406_ADStop(int(icard))  # 防止之前操作未停止
    # 返回值	清FIFO		 拨码ID
    iResult = pDll.USB2406_CLRRAM(int(icard))

    SetADPara()
    ADWork()
    # ------------------------------------- 关闭 -------------------------------------
    # 返回函数调用结果	    关闭卡		    拨码ID
    iResult = pDll.USB2406_CloseDevice(int(icard))
    print("\n卡已关闭")
else:
    print("打开失败")
