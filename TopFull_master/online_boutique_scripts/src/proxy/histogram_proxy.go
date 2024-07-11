// package main

// import (
// 	"log"
// 	"net/http"
// 	"os"
// 	"os/signal"
// 	"syscall"
// 	"bufio"
// 	"strconv"
// 	"io/ioutil"
// 	"strings"
// 	"time"
// 	"fmt"
// 	"sync"
// 	"github.com/elazarl/goproxy"
// )

// var (
// 	limitDir = "/home/jhpark676/online_boutique_scripts/src/proxy/rate_config/"
// 	target_apis = []string{"postcheckout", "getcart", "postcart", "getproduct"}
// 	mapStats = make(map[string]*StatsModule)
// 	globalLock *sync.Mutex
// )

// // Stats Module
// type StatsModule struct {
// 	numReq map[int64]int64
// 	lastReqTimestamp int64
// 	startTimestamp int64

// 	histogram [100]int
// 	target_rps int
// 	priority_threshold int
// 	statsLock *sync.Mutex
// }

// func (stats *StatsModule) Reset() {
// 	stats.statsLock = &sync.Mutex{}
// 	stats.numReq = make(map[int64]int64)
// 	stats.lastReqTimestamp = 0
// 	stats.startTimestamp = time.Now().Unix()

// 	stats.target_rps = 200
// 	stats.priority_threshold = 100
// 	for i, _ := range stats.histogram {
// 		stats.histogram[i] = 0
// 	}
// }

// func (stats *StatsModule) LogRequest(priority int) {
// 	stats.statsLock.Lock()
// 	defer stats.statsLock.Unlock()
// 	currentTime := time.Now().Unix()
// 	num, ok := stats.numReq[currentTime]
// 	if !ok {
// 		stats.numReq[currentTime] = 1
// 	} else {
// 		stats.numReq[currentTime] = num + 1
// 	}
// 	stats.lastReqTimestamp = currentTime

// 	stats.histogram[priority] += 1
// }

// func (stats *StatsModule) CurrentRPS() float64 {
// 	if stats.lastReqTimestamp == 0 {
// 		return 0
// 	}
// 	var startTime int64
// 	currentTime := time.Now().Unix()
// 	if  currentTime - 12 > stats.startTimestamp {
// 		startTime = currentTime - 12
// 	} else {
// 		startTime = stats.startTimestamp
// 	}
	
// 	var total int64
// 	total = 0
// 	for t := startTime; t < currentTime-2; t++ {
// 		req, ok := stats.numReq[t]
// 		if !ok {
// 			total += 0
// 		} else {
// 			total += req
// 		}
// 	}
// 	if currentTime - 2 - startTime == 0 {
// 		return 0
// 	} else {
// 		return float64(total) / float64(currentTime - 2 - startTime)
// 	}
// }

// func (stats *StatsModule) SetTargetRPS(target int) {
// 	stats.statsLock.Lock()
// 	defer stats.statsLock.Unlock()
// 	stats.target_rps = target
// }

// func (stats *StatsModule) SetPriorityThreshold() {
// 	stats.statsLock.Lock()
// 	defer stats.statsLock.Unlock()
// 	tmp := 0
// 	i := 0
// 	for tmp <= stats.target_rps && i < 100 {
// 		tmp += stats.histogram[i]
// 		i += 1
// 	}
// 	stats.priority_threshold = i-1

// 	for j, _ := range stats.histogram {
// 		stats.histogram[j] = 0
// 	}
// }

// func (stats *StatsModule) Allow(r *http.Request) bool {
// 	priority_str, err := r.Header["Priority"]
// 	if !err {
// 		return false
// 	}
// 	priority, _ := strconv.ParseInt(priority_str[0], 10, 32)
// 	stats.LogRequest(int(priority))
// 	if int(priority) > stats.priority_threshold {
// 		return false
// 	} else {
// 		return true
// 	}
// }

// ////////////////////////////////////////////////////////////////

// func init() {
// 	globalLock = &sync.Mutex{}
// 	for _, api := range target_apis {
// 		mapStats[api] = &StatsModule{}
// 		mapStats[api].Reset()
// 	}
// }

// func admissionControl() {
// 	for {
// 		time.Sleep(time.Second)
// 		for _, api := range target_apis {
// 			mapStats[api].SetPriorityThreshold()
// 		}
// 	}
// }

// func changeLimit() {
// 	dir, err := ioutil.ReadDir(limitDir)
// 	if err != nil {
// 		return
// 	}
// 	for _, fInfo := range dir {
// 		api := fInfo.Name()
// 		f, err := os.Open(limitDir + api)
// 		if err != nil {
// 			println("Cannot open" + api)
// 			continue
// 		}
// 		defer f.Close()
// 		scanner := bufio.NewScanner(f)
// 		scanner.Scan()
// 		newRate, err := strconv.ParseInt(scanner.Text(), 10, 32)
// 		if err != nil {
// 			os.Remove(limitDir + api)
// 			print("Wrong rate")
// 			continue
// 		}
		
// 		mapStats[api].SetTargetRPS(int(newRate))

// 		println("Apply threshold to ", api, " : ", newRate)
// 		os.Remove(limitDir + api)
// 	}
// }

// func RejectGetproduct(r *http.Request, ctx *goproxy.ProxyCtx) (*http.Request, *http.Response) {
// 	api := "getproduct"
// 	if mapStats[api].Allow(r) {
// 		return r, nil
// 	} else {
// 		return r, goproxy.NewResponse(r, goproxy.ContentTypeText, http.StatusForbidden, "REJECT!")
// 	}
// }
// func RejectPostcheckout(r *http.Request, ctx *goproxy.ProxyCtx) (*http.Request, *http.Response) {
// 	api := "postcheckout"
// 	if mapStats[api].Allow(r) {
// 		return r, nil
// 	} else {
// 		return r, goproxy.NewResponse(r, goproxy.ContentTypeText, http.StatusForbidden, "REJECT!")
// 	}
// }
// func RejectGetcart(r *http.Request, ctx *goproxy.ProxyCtx) (*http.Request, *http.Response) {
// 	api := "getcart"
// 	if mapStats[api].Allow(r) {
// 		return r, nil
// 	} else {
// 		return r, goproxy.NewResponse(r, goproxy.ContentTypeText, http.StatusForbidden, "REJECT!")
// 	}
// }
// func RejectPostcart(r *http.Request, ctx *goproxy.ProxyCtx) (*http.Request, *http.Response) {
// 	api := "postcart"
// 	if mapStats[api].Allow(r) {
// 		return r, nil
// 	} else {
// 		return r, goproxy.NewResponse(r, goproxy.ContentTypeText, http.StatusForbidden, "REJECT!")
// 	}
// }
// func ReqStat(r *http.Request, ctx *goproxy.ProxyCtx) (*http.Request, *http.Response) {
// 	out := ""
// 	for _, api := range target_apis {
// 		out += fmt.Sprintf("%s=%.1f/", api, mapStats[api].CurrentRPS())
// 	}
// 	return r, goproxy.NewResponse(r, goproxy.ContentTypeText, http.StatusOK, out)
// }
// func ReqThreshold(r *http.Request, ctx *goproxy.ProxyCtx) (*http.Request, *http.Response) {
// 	out := ""
// 	for _, api := range target_apis {
// 		out += fmt.Sprintf("%s=%d/", api, mapStats[api].target_rps)
// 	}
// 	return r, goproxy.NewResponse(r, goproxy.ContentTypeText, http.StatusOK, out)
// }


// var GetCartCondition goproxy.ReqConditionFunc = func (req *http.Request, ctx *goproxy.ProxyCtx) bool {
// 	return req.URL.Host == "egg3.kaist.ac.kr:30440" &&
// 			req.Method == "GET"  &&
// 			req.URL.Path == "/cart"
// }
// var PostCartCondition goproxy.ReqConditionFunc = func (req *http.Request, ctx *goproxy.ProxyCtx) bool {
// 	return req.URL.Host == "egg3.kaist.ac.kr:30440" &&
// 			req.Method == "POST"  &&
// 			req.URL.Path == "/cart"
// }
// var PostCheckoutCondition goproxy.ReqConditionFunc = func (req *http.Request, ctx *goproxy.ProxyCtx) bool {
// 	return req.URL.Host == "egg3.kaist.ac.kr:30440" &&
// 			req.Method == "POST"  &&
// 			req.URL.Path == "/cart/checkout"
// }
// var GetProductCondition goproxy.ReqConditionFunc = func (req *http.Request, ctx *goproxy.ProxyCtx) bool {
// 	return req.URL.Host == "egg3.kaist.ac.kr:30440" &&
// 			req.Method == "GET"  &&
// 			strings.Contains(req.URL.Path, "/product")
// }
// var ReqStatCondition goproxy.ReqConditionFunc = func (req *http.Request, ctx *goproxy.ProxyCtx) bool {
// 	return req.Method == "GET"  &&
// 			strings.Contains(req.URL.Path, "/stats")
// }
// var ReqThresholdCondition goproxy.ReqConditionFunc = func (req *http.Request, ctx *goproxy.ProxyCtx) bool {
// 	return req.Method == "GET"  &&
// 			strings.Contains(req.URL.Path, "/thresholds")
// }

// func main() {
// 	sigs := make(chan os.Signal, 1)
// 	signal.Notify(sigs, syscall.SIGUSR1)
// 	go func() {
// 		for {
// 			sig := <-sigs
// 			println("Get signal", sig)
// 			changeLimit()
// 		}
// 	}()

// 	// go monitorRPS()
// 	go admissionControl()
// 	proxy := goproxy.NewProxyHttpServer()
// 	proxy.Verbose = false

// 	// proxy.OnRequest(goproxy.DstHostIs("egg3.kaist.ac.kr:30440")).DoFunc(Reject)

// 	proxy.OnRequest(GetCartCondition).DoFunc(RejectGetcart)
// 	proxy.OnRequest(GetProductCondition).DoFunc(RejectGetproduct)
// 	proxy.OnRequest(PostCartCondition).DoFunc(RejectPostcart)
// 	proxy.OnRequest(PostCheckoutCondition).DoFunc(RejectPostcheckout)
// 	proxy.OnRequest(ReqStatCondition).DoFunc(ReqStat)
// 	proxy.OnRequest(ReqThresholdCondition).DoFunc(ReqThreshold)
	
// 	log.Fatal(http.ListenAndServe(":8090", proxy))
// }