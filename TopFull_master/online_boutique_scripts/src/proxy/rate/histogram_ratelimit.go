package rate

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

	"github.com/elazarl/goproxy"

	"golang.org/x/time/rate"
)

var (
	limitDir = "/home/master_artifact/TopFull/online_boutique_scripts/src/proxy/rate_config/"
	target_apis = []string{"postcheckout", "getcart", "postcart", "getproduct"}

	bound = 100
	histograms = make(map[string][100]int)
	target_thresholds = make(map[string]int)
	real_thresholds = make(map[string]int)
	mapStats = make(map[string]*StatsModule)
	globalLock *sync.Mutex
	admissionLock *sync.Mutex
)

func init() {
	globalLock = &sync.Mutex{}
	admissionLock = &sync.Mutex{}
	for _, elem := range target_apis {
		histograms[elem] = [100]int{}
		target_thresholds[elem] = 101
		real_thresholds[elem] = 101
	}

	mapStats["postcheckout"] = &StatsModule{}
	mapStats["getproduct"] = &StatsModule{}
	mapStats["getcart"] = &StatsModule{}
	mapStats["postcart"] = &StatsModule{}
	mapStats["postcheckout"].reset()
	mapStats["getproduct"].reset()
	mapStats["getcart"].reset()
	mapStats["postcart"].reset()
}

// For every interval, try to match thresholds according to histogram
func admissionControl() {
	for {
		time.Sleep(1 * time.Second)
		admissionLock.Lock()
		defer admissionLock.Unlock()
		
		for _, elem := range target_apis {
			target := target_thresholds[elem]
			tmp := 0
			i := 0
			for tmp <= target && i < 100 {
				tmp += histograms[elem][i]
				i += 1
			}
			real_thresholds[elem] = i-1

			for j, _ := range histograms[elem] {
				histograms[elem][j] = 0
			}
		}
	}
}

func admissionControlNow(elem string) {
	admissionLock.Lock()
	defer admissionLock.Unlock()
	target := target_thresholds[elem]
	tmp := 0
	i := 0
	for tmp <= target && i < 100 {
		tmp += histograms[elem][i]
		i += 1
	}
	real_thresholds[elem] = i-1
}


type StatsModule struct {
	numReq map[int64]int64
	lastReqTimestamp int64
	startTimestamp int64
}

func (stats *StatsModule) reset() {
	stats.numReq = make(map[int64]int64)
	stats.lastReqTimestamp = 0
	stats.startTimestamp = time.Now().Unix()
}

func (stats *StatsModule) logRequest() {
	globalLock.Lock()
	defer globalLock.Unlock()
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
	if stats.lastReqTimestamp == 0 {
		return 0
	}
	var startTime int64
	currentTime := time.Now().Unix()
	if  currentTime - 12 > stats.startTimestamp {
		startTime = currentTime - 12
	} else {
		startTime = stats.startTimestamp
	}
	
	var total int64
	total = 0
	for t := startTime; t < currentTime-2; t++ {
		req, ok := stats.numReq[t]
		if !ok {
			total += 0
		} else {
			total += req
		}
	}
	if currentTime - 2 - startTime == 0 {
		return 0
	} else {
		return float64(total) / float64(currentTime - 2 - startTime)
	}
}


func monitorRPS() {
	fmt.Printf("Start monitoring\n")
	for true {
		time.Sleep(5 * time.Second)
		fmt.Printf("-------------------------\n")
		fmt.Printf("postcompose: %.1f\n", mapStats["postcompose"].currentRPS())
		fmt.Printf("getuser: %.1f\n", mapStats["getuser"].currentRPS())
		fmt.Printf("gethome: %.1f\n", mapStats["gethome"].currentRPS())
	}
}



func changeLimitAbs() {
	dir, err := ioutil.ReadDir(limitDir)
	if err != nil {
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
		newRate, err := strconv.ParseInt(scanner.Text(), 10, 32)
		if err != nil {
			os.Remove(limitDir + api)
			print("Wrong rate")
			continue
		}
		
		target_thresholds[api] = int(newRate)
		admissionControlNow(api)

		println("Apply threshold to ", api, " : ", newRate)
		os.Remove(limitDir + api)
	}
}

func RejectGetproduct(r *http.Request, ctx *goproxy.ProxyCtx) (*http.Request, *http.Response) {
	target := "getproduct"
	mapStats[target].logRequest()
	priority_str, err := r.Header["Priority"]
	if !err {
		return r, goproxy.NewResponse(r, goproxy.ContentTypeText, http.StatusForbidden, "REJECT!")
	}
	priority, _ := strconv.ParseInt(priority_str[0], 10, 32)
	if int(priority) <= real_thresholds[target] {
		return r, nil
	} else {
		return r, goproxy.NewResponse(r, goproxy.ContentTypeText, http.StatusForbidden, "REJECT!")
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


func ReqStat(r *http.Request, ctx *goproxy.ProxyCtx) (*http.Request, *http.Response) {
	out := ""
	out += fmt.Sprintf("postcheckout=%.1f/", mapStats["postcheckout"].currentRPS())
	out += fmt.Sprintf("getproduct=%.1f/", mapStats["getproduct"].currentRPS())
	out += fmt.Sprintf("getcart=%.1f/", mapStats["getcart"].currentRPS())
	out += fmt.Sprintf("postcart=%.1f/", mapStats["postcart"].currentRPS())
	return r, goproxy.NewResponse(r, goproxy.ContentTypeText, http.StatusOK, out)
	
}

func ReqThreshold(r *http.Request, ctx *goproxy.ProxyCtx) (*http.Request, *http.Response) {
	out := ""
	apis := []string{"postcheckout", "getproduct", "getcart", "postcart"}
	for _, elem := range apis {
		out += fmt.Sprintf("%s=%.1f/", elem, float64(limiterTable[elem].Limit()))
	}
	return r, goproxy.NewResponse(r, goproxy.ContentTypeText, http.StatusOK, out)
}




var GetCartCondition goproxy.ReqConditionFunc = func (req *http.Request, ctx *goproxy.ProxyCtx) bool {
	return req.URL.Host == "egg3.kaist.ac.kr:30440" &&
			req.Method == "GET"  &&
			req.URL.Path == "/cart"
}
var PostCartCondition goproxy.ReqConditionFunc = func (req *http.Request, ctx *goproxy.ProxyCtx) bool {
	return req.URL.Host == "egg3.kaist.ac.kr:30440" &&
			req.Method == "POST"  &&
			req.URL.Path == "/cart"
}
var PostCheckoutCondition goproxy.ReqConditionFunc = func (req *http.Request, ctx *goproxy.ProxyCtx) bool {
	return req.URL.Host == "egg3.kaist.ac.kr:30440" &&
			req.Method == "POST"  &&
			req.URL.Path == "/cart/checkout"
}
var GetProductCondition goproxy.ReqConditionFunc = func (req *http.Request, ctx *goproxy.ProxyCtx) bool {
	return req.URL.Host == "egg3.kaist.ac.kr:30440" &&
			req.Method == "GET"  &&
			strings.Contains(req.URL.Path, "/product")
}

var ReqStatCondition goproxy.ReqConditionFunc = func (req *http.Request, ctx *goproxy.ProxyCtx) bool {
	return req.Method == "GET"  &&
			strings.Contains(req.URL.Path, "/stats")
}
var ReqThresholdCondition goproxy.ReqConditionFunc = func (req *http.Request, ctx *goproxy.ProxyCtx) bool {
	return req.Method == "GET"  &&
			strings.Contains(req.URL.Path, "/thresholds")
}

