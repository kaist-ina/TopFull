package main

import (
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"bufio"
	"strconv"
	"io/ioutil"
	"strings"
	"time"
	"fmt"
	"sync"
	"encoding/json"
	"github.com/elazarl/goproxy"

	"golang.org/x/time/rate"
)



var (
	limiter = rate.NewLimiter(70, 70)
	limitDir string
	limiterTable = make(map[string]*rate.Limiter)
	global_config_path = "/home/master_artifact/TopFull/online_boutique_scripts/src/global_config.json"
	global_config Config
	mapStats = make(map[string]*StatsModule)
	globalLock *sync.Mutex
)
type Config struct {
	ProxyDir string `json:"proxy_dir"`
	FrontendUrl string `json:"frontend_url"`
	TargetAPI []string `json:"record_target"`
}

type StatsModule struct {
	numReq map[int64]int64
	lastReqTimestamp int64
	startTimestamp int64
	localLock *sync.Mutex
}

func (stats *StatsModule) reset() {
	stats.numReq = make(map[int64]int64)
	stats.lastReqTimestamp = 0
	stats.startTimestamp = time.Now().Unix()
	stats.localLock = &sync.Mutex{}
}

func (stats *StatsModule) logRequest() {
	stats.localLock.Lock()
	defer stats.localLock.Unlock()
	currentTime := time.Now().Unix()
	num, ok := stats.numReq[currentTime]
	if !ok {
		stats.numReq[currentTime] = 1
		} else {
			stats.numReq[currentTime] = num + 1
		}
		stats.lastReqTimestamp = currentTime
	}
	
	func (stats *StatsModule) currentRPS() float64 {
	stats.localLock.Lock()
	defer stats.localLock.Unlock()
	if stats.lastReqTimestamp == 0 {
		return 0
	}
	var startTime int64
	currentTime := time.Now().Unix()
	if  currentTime - 4 > stats.startTimestamp {
		startTime = currentTime - 4
	} else {
		startTime = stats.startTimestamp
	}
	
	var total int64
	total = 0
	for t := startTime; t < currentTime; t++ {
		req, ok := stats.numReq[t]
		if !ok {
			total += 0
		} else {
			total += req
		}
	}
	if currentTime - startTime == 0 {
		return 0
	} else {
		return float64(total) / float64(currentTime - startTime)
	}
}

func init() {
	b, err := ioutil.ReadFile(global_config_path)
	if err != nil {
		fmt.Println(err)
	}
	json.Unmarshal(b, &global_config)

	limitDir = global_config.ProxyDir

	
	for _, elem := range global_config.TargetAPI {
		limiterTable[elem] = rate.NewLimiter(10000, 10000)
		limiterTable[elem].SetBurst(10000)

		mapStats[elem] = &StatsModule{}
		mapStats[elem].reset()
	}


	globalLock = &sync.Mutex{}

}

func monitorRPS() {
	fmt.Printf("Start monitoring\n")
	for true {
		time.Sleep(1 * time.Second)
		fmt.Printf("-------------------------\n")
		for _, elem := range global_config.TargetAPI {
			fmt.Printf("%s: %.1f ", elem, mapStats[elem].currentRPS())
			fmt.Printf("\n")
		}
	}
}


func changeLimitDelta() {
	dir, err := ioutil.ReadDir(limitDir)
	if err != nil {
		return
	}
	for _, fInfo := range dir {
		api := fInfo.Name()
		f, err := os.Open(limitDir + api)
		if err != nil {
			continue
		}
		defer f.Close()
		scanner := bufio.NewScanner(f)
		scanner.Scan()
		newRate, err := strconv.ParseFloat(scanner.Text(), 64)
		if err != nil {
			os.Remove(limitDir + api)
			continue
		}
		
		targetLimiter, ok := limiterTable[api]
		if !ok {
			println("Wrong API")
			os.Remove(limitDir + api)
			continue
		}
		currentRate := float64(targetLimiter.Limit())
		newRateFloat := newRate + currentRate
		if newRateFloat <= 0.0 {
			println("Too low threshold")
			os.Remove(limitDir + api)
			continue
		}
		
		targetLimiter.SetLimit(rate.Limit(newRateFloat))
		targetLimiter.SetBurst(int(newRateFloat))
		println("Apply threshold to ", api, " : ", newRateFloat)
		os.Remove(limitDir + api)
	}
}


func changeLimitAbs() {
	dir, err := ioutil.ReadDir(limitDir)
	if err != nil {
		println("Cannot read dir")
		return
	}
	for _, fInfo := range dir {
		api := fInfo.Name()
		f, err := os.Open(limitDir + api)
		if err != nil {
			println("Cannot open" + api)
			continue
		}
		defer f.Close()
		scanner := bufio.NewScanner(f)
		scanner.Scan()
		newRate, err := strconv.ParseFloat(scanner.Text(), 64)
		if err != nil {
			os.Remove(limitDir + api)
			print("Wrong rate")
			continue
		}
		
		targetLimiter, ok := limiterTable[api]
		if !ok {
			println("Wrong API")
			os.Remove(limitDir + api)
			continue
		}
		
		targetLimiter.SetLimit(rate.Limit(float64(newRate)))
		targetLimiter.SetBurst(int(newRate))
		println("Apply threshold to ", api, " : ", newRate)
		os.Remove(limitDir + api)
	}
}

func RejectGetproduct(r *http.Request, ctx *goproxy.ProxyCtx) (*http.Request, *http.Response) {
	mapStats["getproduct"].logRequest()
	if limiterTable["getproduct"].Allow() == false {
		return r, goproxy.NewResponse(r, goproxy.ContentTypeText, http.StatusForbidden, "REJECT!")
	} else {
		return r, nil
	}
}
func RejectPostcheckout(r *http.Request, ctx *goproxy.ProxyCtx) (*http.Request, *http.Response) {
	mapStats["postcheckout"].logRequest()
	if limiterTable["postcheckout"].Allow() == false {
		return r, goproxy.NewResponse(r, goproxy.ContentTypeText, http.StatusForbidden, "REJECT!")
	} else {
		return r, nil
	}
}
func RejectGetcart(r *http.Request, ctx *goproxy.ProxyCtx) (*http.Request, *http.Response) {
	mapStats["getcart"].logRequest()
	if limiterTable["getcart"].Allow() == false {
		return r, goproxy.NewResponse(r, goproxy.ContentTypeText, http.StatusForbidden, "REJECT!")
	} else {
		return r, nil
	}
}
func RejectPostcart(r *http.Request, ctx *goproxy.ProxyCtx) (*http.Request, *http.Response) {
	mapStats["postcart"].logRequest()
	if limiterTable["postcart"].Allow() == false {
		return r, goproxy.NewResponse(r, goproxy.ContentTypeText, http.StatusForbidden, "REJECT!")
	} else {
		return r, nil
	}
}
func RejectEmptycart(r *http.Request, ctx *goproxy.ProxyCtx) (*http.Request, *http.Response) {
	mapStats["emptycart"].logRequest()
	if limiterTable["emptycart"].Allow() == false {
		return r, goproxy.NewResponse(r, goproxy.ContentTypeText, http.StatusForbidden, "REJECT!")
	} else {
		return r, nil
	}
}


func ReqStat(r *http.Request, ctx *goproxy.ProxyCtx) (*http.Request, *http.Response) {
	target_apis := global_config.TargetAPI
	out := ""
	for _, elem := range target_apis {
		out += fmt.Sprintf("%s=%1.f/", elem, mapStats[elem].currentRPS())
	}

	return r, goproxy.NewResponse(r, goproxy.ContentTypeText, http.StatusOK, out)
	
}

func ReqThreshold(r *http.Request, ctx *goproxy.ProxyCtx) (*http.Request, *http.Response) {
	out := ""
	apis := global_config.TargetAPI
	for _, elem := range apis {
		out += fmt.Sprintf("%s=%.1f/", elem, float64(limiterTable[elem].Limit()))
	}
	return r, goproxy.NewResponse(r, goproxy.ContentTypeText, http.StatusOK, out)
}




var GetCartCondition goproxy.ReqConditionFunc = func (req *http.Request, ctx *goproxy.ProxyCtx) bool {
	return req.URL.Host == global_config.FrontendUrl &&
			req.Method == "GET"  &&
			req.URL.Path == "/cart"
}
var PostCartCondition goproxy.ReqConditionFunc = func (req *http.Request, ctx *goproxy.ProxyCtx) bool {	
	return req.URL.Host == global_config.FrontendUrl &&
			req.Method == "POST"  &&
			req.URL.Path == "/cart"
}
var PostCheckoutCondition goproxy.ReqConditionFunc = func (req *http.Request, ctx *goproxy.ProxyCtx) bool {
	return req.URL.Host == global_config.FrontendUrl &&
			req.Method == "POST"  &&
			req.URL.Path == "/cart/checkout"
}
var GetProductCondition goproxy.ReqConditionFunc = func (req *http.Request, ctx *goproxy.ProxyCtx) bool {
	return req.URL.Host == global_config.FrontendUrl &&
			req.Method == "GET"  &&
			strings.Contains(req.URL.Path, "/product")
}
var EmptyCartCondition goproxy.ReqConditionFunc = func (req *http.Request, ctx *goproxy.ProxyCtx) bool {
	return req.URL.Host == global_config.FrontendUrl &&
			req.Method == "POST"  &&
			req.URL.Path == "/cart/empty"
}


var ReqStatCondition goproxy.ReqConditionFunc = func (req *http.Request, ctx *goproxy.ProxyCtx) bool {
	return req.Method == "GET"  &&
			strings.Contains(req.URL.Path, "/stats")
}
var ReqThresholdCondition goproxy.ReqConditionFunc = func (req *http.Request, ctx *goproxy.ProxyCtx) bool {
	return req.Method == "GET"  &&
			strings.Contains(req.URL.Path, "/thresholds")
}

func main() {
	sigs := make(chan os.Signal, 1)
	signal.Notify(sigs, syscall.SIGUSR1)
	go func() {
		for {
			sig := <-sigs
			println("Get signal", sig)
			changeLimitAbs()
		}
	}()

	go monitorRPS()

	proxy := goproxy.NewProxyHttpServer()
	proxy.Verbose = false
	proxy.Tr.MaxIdleConns = 50000
	proxy.Tr.MaxIdleConnsPerHost = 50000



	proxy.OnRequest(GetCartCondition).DoFunc(RejectGetcart)
	proxy.OnRequest(GetProductCondition).DoFunc(RejectGetproduct)
	proxy.OnRequest(PostCartCondition).DoFunc(RejectPostcart)
	proxy.OnRequest(EmptyCartCondition).DoFunc(RejectEmptycart)
	proxy.OnRequest(PostCheckoutCondition).DoFunc(RejectPostcheckout)
	

	proxy.OnRequest(ReqStatCondition).DoFunc(ReqStat)
	proxy.OnRequest(ReqThresholdCondition).DoFunc(ReqThreshold)
	println("Start")
	log.Fatal(http.ListenAndServe(":8090", proxy))
}
